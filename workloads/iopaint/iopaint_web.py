"""Headless Python port of the IOPaint web client (Sanster/IOPaint @ 61a759f, web_app/src).

It sends the API requests that the browser app sends on the editing path of
this workload, in the same order and with the same bodies, built from the same
store state. Each function names the upstream code it mirrors; line numbers
refer to the pinned commit.

  lib/api.ts         transport: getServerConfig, currentModel, getGenInfo, runPlugin,
                     inpaint, postAdjustMask, downloadToOutput
  lib/states.ts      editor store: setServerConfig, updateSettings, setFile, setImageSize,
                     runInpainting, runRenderablePlugin, getCurrentTargetFile,
                     handleInteractiveSegAccept, adjustMask
  App.tsx, components/Workspace.tsx   page-load requests
  components/Editor.tsx               getCurrentRender, runInteractiveSeg,
                                      onCanvasMouseUp (interactive-seg clicks), download
  components/Plugins.tsx              plugin menu (interactive seg toggle, RealESRGAN 2x)
  lib/utils.ts       generateMask, drawLines, convertToBase64 (FileReader.readAsDataURL),
                     srcToFile, dataURItoBlob, canvasToImage

Browser objects are modelled minimally: a File/Blob is bytes plus a name and a
MIME type; an HTMLImageElement keeps the bytes it was loaded from
(`currentSrc`) and its decoded size; a canvas is a Pillow RGBA bitmap whose
toDataURL() is a Pillow-encoded PNG. Toasts are recorded, not shown.

What the port does not do (see the workload card): it does not load the
static web UI, does not open the socket.io connection of the UI's progress bar,
and does not send two page-load GETs whose
responses no later request uses (GET /api/v1/inputimage from App.tsx:28 via
hooks/useInputImage.tsx:12, and the Settings dialog's GET /api/v1/server-config,
components/Settings.tsx:97-104). Two settings defaults differ from the browser's,
see DEFAULT_SETTINGS.
"""
import base64
import copy
import io
import json

from PIL import Image, ImageColor, ImageDraw

API_PATH = "/api/v1"               # lib/api.ts:13-15 (production build)
BRUSH_COLOR = "#ffcc00bb"          # lib/const.ts:11
MODEL_TYPE_INPAINT = "inpaint"     # lib/const.ts:5
DEFAULT_BRUSH_SIZE = 40            # lib/const.ts:2


# ---------------------------------------------------------------- browser primitives
class File:
    """File / Blob: bytes plus the name and MIME type the browser attaches."""

    def __init__(self, data, name="blob", type=""):
        self.data, self.name, self.type = data, name, type


class HTMLImage:
    """`new Image()` after loadImage(img, objectURL) (lib/utils.ts:43-54): source bytes, decoded size."""

    def __init__(self, data):
        self.currentSrc = data
        self.src = data
        with Image.open(io.BytesIO(data)) as im:
            self.width, self.height = im.size

    def bitmap(self):
        with Image.open(io.BytesIO(self.currentSrc)) as im:
            return im.convert("RGBA")


class Canvas:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.bitmap = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    def toDataURL(self):
        buf = io.BytesIO()
        self.bitmap.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def js_json(value):
    """JSON.stringify: no whitespace, `undefined` keys dropped, integral numbers without '.0'."""
    def norm(v):
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, dict):
            return {k: norm(x) for k, x in v.items() if x is not UNDEFINED}
        if isinstance(v, list):
            return [norm(x) for x in v]
        return v
    return json.dumps(norm(value), separators=(",", ":"), ensure_ascii=False)


UNDEFINED = object()


# ---------------------------------------------------------------- lib/utils.ts
def convertToBase64(fileOrBlob):
    """lib/utils.ts:244-256, FileReader.readAsDataURL."""
    return "data:" + (fileOrBlob.type or "application/octet-stream") + ";base64," + \
        base64.b64encode(fileOrBlob.data).decode()


def dataURItoBlob(dataURI):
    """lib/utils.ts:33-41."""
    header, b64 = dataURI.split(",", 1)
    return File(base64.b64decode(b64), "blob", header.split(":")[1].split(";")[0])


def srcToFile(src, fileName, mimeType):
    """lib/utils.ts:101-109: fetch(objectURL) -> arrayBuffer -> new File([buf], fileName, {type: mimeType})."""
    return File(src, fileName, mimeType)


def canvasToImage(canvas):
    """lib/utils.ts:63-79."""
    return HTMLImage(dataURItoBlob(canvas.toDataURL()).data)


def drawLines(ctx_canvas, lines, color=BRUSH_COLOR):
    """lib/utils.ts:197-216 (round caps and joins)."""
    draw = ImageDraw.Draw(ctx_canvas.bitmap, "RGBA")
    rgba = ImageColor.getrgb(color)
    for line in lines:
        pts = [(p["x"], p["y"]) for p in line["pts"]]
        if len(pts) == 1:
            pts = pts * 2
        draw.line(pts, fill=rgba, width=int(line["size"]), joint="curve")
        r = line["size"] / 2
        for x, y in (pts[0], pts[-1]):
            draw.ellipse((x - r, y - r, x + r, y + r), fill=rgba)


def generateMask(imageWidth, imageHeight, lineGroups, maskImages=(), lineGroupsColor="white"):
    """lib/utils.ts:218-242: draw the mask images, then the strokes, on a transparent canvas."""
    maskCanvas = Canvas(imageWidth, imageHeight)
    for maskImage in maskImages:
        layer = maskImage.bitmap()
        if layer.size != (imageWidth, imageHeight):
            layer = layer.resize((imageWidth, imageHeight))
        maskCanvas.bitmap.alpha_composite(layer)
    for lineGroup in lineGroups:
        drawLines(maskCanvas, lineGroup, lineGroupsColor)
    return maskCanvas


# ---------------------------------------------------------------- lib/api.ts
class Api:
    def __init__(self, base_url, session):
        self.endpoint = base_url.rstrip("/") + API_PATH
        self.http = session

    @staticmethod
    def _throw(res):
        """lib/api.ts:21-26 (throwErrors)."""
        raise RuntimeError(f"{res.status_code}: {res.text[:300]}")

    def inpaint(self, imageFile, settings, croperRect, extenderState, mask, paintByExampleImage=None):
        """lib/api.ts:28-103: POST /inpaint, JSON body; the response is the image, X-Seed header."""
        imageBase64 = convertToBase64(imageFile)
        maskBase64 = convertToBase64(mask)
        exampleImageBase64 = convertToBase64(paintByExampleImage) if paintByExampleImage else None
        s = settings
        body = {
            "image": imageBase64,
            "mask": maskBase64,
            "ldm_steps": s["ldmSteps"],
            "ldm_sampler": s["ldmSampler"],
            "zits_wireframe": s["zitsWireframe"],
            "cv2_flag": s["cv2Flag"],
            "cv2_radius": s["cv2Radius"],
            "hd_strategy": "Crop",
            "hd_strategy_crop_triger_size": 640,
            "hd_strategy_crop_margin": 128,
            "hd_trategy_resize_imit": 2048,
            "prompt": s["prompt"],
            "negative_prompt": s["negativePrompt"],
            "use_croper": s["showCropper"],
            "croper_x": croperRect["x"],
            "croper_y": croperRect["y"],
            "croper_height": croperRect["height"],
            "croper_width": croperRect["width"],
            "use_extender": s["showExtender"],
            "extender_x": extenderState["x"],
            "extender_y": extenderState["y"],
            "extender_height": extenderState["height"],
            "extender_width": extenderState["width"],
            "sd_mask_blur": s["sdMaskBlur"],
            "sd_strength": s["sdStrength"],
            "sd_steps": s["sdSteps"],
            "sd_guidance_scale": s["sdGuidanceScale"],
            "sd_sampler": s["sdSampler"],
            "sd_seed": s["seed"] if s["seedFixed"] else -1,
            "sd_match_histograms": s["sdMatchHistograms"],
            "sd_lcm_lora": s["enableLCMLora"],
            "paint_by_example_example_image": exampleImageBase64,
            "p2p_image_guidance_scale": s["p2pImageGuidanceScale"],
            "enable_controlnet": s["enableControlnet"],
            "controlnet_conditioning_scale": s["controlnetConditioningScale"],
            "controlnet_method": s["controlnetMethod"] if s["controlnetMethod"] else "",
            "enable_brushnet": s["enableBrushNet"],
            "brushnet_method": s["brushnetMethod"] if s["brushnetMethod"] else "",
            "brushnet_conditioning_scale": s["brushnetConditioningScale"],
            "enable_powerpaint_v2": s["enablePowerPaintV2"],
            "powerpaint_task": "outpainting" if s["showExtender"] else s["powerpaintTask"],
        }
        res = self.http.post(self.endpoint + "/inpaint", data=js_json(body),
                             headers={"Content-Type": "application/json"})
        if res.ok:
            return {"blob": res.content, "seed": res.headers.get("X-Seed")}
        self._throw(res)

    def getServerConfig(self):
        """lib/api.ts:105-108: GET /server-config."""
        return self.http.get(self.endpoint + "/server-config").json()

    def currentModel(self):
        """lib/api.ts:122-125: GET /model."""
        return self.http.get(self.endpoint + "/model").json()

    def runPlugin(self, genMask, name, imageFile, upscale=UNDEFINED, clicks=UNDEFINED):
        """lib/api.ts:127-153: POST /run_plugin_gen_mask or /run_plugin_gen_image, JSON body."""
        imageBase64 = convertToBase64(imageFile)
        p = "run_plugin_gen_mask" if genMask else "run_plugin_gen_image"
        res = self.http.post(self.endpoint + "/" + p,
                             data=js_json({"name": name, "image": imageBase64, "scale": upscale, "clicks": clicks}),
                             headers={"Content-Type": "application/json"})
        if res.ok:
            return {"blob": res.content}
        self._throw(res)

    def downloadToOutput(self, image, filename, mimeType):
        """lib/api.ts:195-215: POST /save_image, multipart form with one file part."""
        file = srcToFile(image.src, filename, mimeType)
        res = self.http.post(self.endpoint + "/save_image", files={"file": (file.name, file.data, file.type)})
        if not res.ok:
            self._throw(res)

    def getGenInfo(self, file):
        """lib/api.ts:217-222: POST /gen-info, multipart form with the opened file."""
        res = self.http.post(self.endpoint + "/gen-info", files={"file": (file.name, file.data, file.type)})
        if not res.ok:
            self._throw(res)
        return res.json()

    def postAdjustMask(self, mask, operate, kernel_size):
        """lib/api.ts:229-251 (not used by this workload)."""
        maskBase64 = convertToBase64(mask)
        res = self.http.post(self.endpoint + "/adjust_mask",
                             data=js_json({"mask": maskBase64, "operate": operate, "kernel_size": kernel_size}),
                             headers={"Content-Type": "application/json"})
        if res.ok:
            return File(res.content, "blob", res.headers.get("Content-Type", ""))
        self._throw(res)


# ---------------------------------------------------------------- lib/states.ts (store)
# defaultValues.settings (lib/states.ts:314-364), the fields the requests read. Two values
# are those of the client the workload was developed and measured with, and differ from
# the browser's defaults; neither field is used by the LaMa model, so the images do not
# change, only the size of each /inpaint body:
#   negativePrompt   browser: DEFAULT_NEGATIVE_PROMPT (lib/const.ts:22-23, 283 characters); here ""
#   controlnetMethod browser: replaced by server-config's controlnetMethod (null for LaMa) in
#                    setServerConfig (lib/states.ts:797-803), so the browser sends
#                    "controlnet_method": ""; here the default below is kept and sent.
DEFAULT_SETTINGS = {
    "model": {"name": "lama", "path": "lama", "model_type": "inpaint", "support_outpainting": False},
    "showCropper": False, "showExtender": False, "enableManualInpainting": False,
    "enableAutoExtractPrompt": True, "ldmSteps": 30, "ldmSampler": "ddim", "zitsWireframe": True,
    "cv2Radius": 5, "cv2Flag": "INPAINT_NS", "prompt": "", "negativePrompt": "", "seed": 42,
    "seedFixed": False, "sdMaskBlur": 12, "sdStrength": 1.0, "sdSteps": 50, "sdGuidanceScale": 7.5,
    "sdSampler": "DPM++ 2M", "sdMatchHistograms": False, "sdScale": 1.0, "p2pImageGuidanceScale": 1.5,
    "enableControlnet": False, "controlnetMethod": "lllyasviel/control_v11p_sd15_canny",
    "controlnetConditioningScale": 0.4, "enableBrushNet": False, "brushnetMethod": "random_mask",
    "brushnetConditioningScale": 1.0, "enableLCMLora": False, "enablePowerPaintV2": False,
    "powerpaintTask": "text-guided", "adjustMaskKernelSize": 12,
}
DEFAULT_EDITOR_STATE = {  # lib/states.ts:254-267
    "baseBrushSize": DEFAULT_BRUSH_SIZE, "brushSizeScale": 1, "renders": [], "extraMasks": [],
    "prevExtraMasks": [], "temporaryMasks": [], "lineGroups": [], "lastLineGroup": [],
    "curLineGroup": [], "redoRenders": [], "redoCurLines": [], "redoLineGroups": [],
}
DEFAULT_INTERACTIVE_SEG = {"isInteractiveSeg": False, "tmpInteractiveSegMask": None, "clicks": []}  # :269-273


class Store:
    """useStore (lib/states.ts): the slice of AppState the requests depend on, with the same actions."""

    def __init__(self, api):
        self.api = api
        self.file = None
        self.paintByExampleFile = None
        self.imageWidth = self.imageHeight = 0
        self.isInpainting = self.isPluginRunning = self.isAdjustingMask = False
        self.editorState = copy.deepcopy(DEFAULT_EDITOR_STATE)
        self.interactiveSegState = copy.deepcopy(DEFAULT_INTERACTIVE_SEG)
        self.cropperState = {"x": 0, "y": 0, "width": 512, "height": 512}     # :275-280
        self.extenderState = {"x": 0, "y": 0, "width": 512, "height": 512}    # :281-286
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.serverConfig = {"enableAutoSaving": False}                      # :297-313
        self.toasts = []

    def toast(self, description, variant=None):
        self.toasts.append((variant, description))

    # --- App.tsx / Workspace.tsx mount effects
    def setServerConfig(self, newValue):
        """lib/states.ts:797-803 (only serverConfig is kept; see DEFAULT_SETTINGS)."""
        self.serverConfig = newValue

    def updateSettings(self, newSettings):
        """lib/states.ts:805-812."""
        self.settings.update(newSettings)

    def setSeed(self, newValue):
        """lib/states.ts:1097-1100."""
        self.settings["seed"] = newValue

    def setFile(self, file):
        """lib/states.ts:922-951: gen-info of the opened file, then reset the editor."""
        if self.settings["enableAutoExtractPrompt"]:
            try:
                res = self.api.getGenInfo(file)
                if res.get("prompt"):
                    self.settings["prompt"] = res["prompt"]
                if res.get("negative_prompt"):
                    self.settings["negativePrompt"] = res["negative_prompt"]
            except Exception as e:
                self.toast(str(e), "destructive")
        self.file = file
        self.interactiveSegState = copy.deepcopy(DEFAULT_INTERACTIVE_SEG)
        self.editorState = copy.deepcopy(DEFAULT_EDITOR_STATE)
        self.cropperState = {"x": 0, "y": 0, "width": 512, "height": 512}

    def setImageSize(self, width, height):
        """lib/states.ts:981-990."""
        self.imageWidth, self.imageHeight = width, height
        self.editorState["brushSizeScale"] = max(min(width, height), 512) / 512
        self.resetExtender(width, height)

    def resetExtender(self, width, height):
        """lib/states.ts:1088-1095."""
        self.extenderState.update({"x": 0, "y": 0, "width": width, "height": height})

    def updateEditorState(self, **newState):
        """lib/states.ts:621-625."""
        self.editorState = {**self.editorState, **newState}

    def updateInteractiveSegState(self, **newState):
        """lib/states.ts:878-888."""
        self.interactiveSegState = {**self.interactiveSegState, **newState}

    def resetRedoState(self):
        """lib/states.ts:769-775."""
        self.editorState.update({"redoCurLines": [], "redoLineGroups": [], "redoRenders": []})

    def runMannually(self):
        """lib/states.ts:652-658 (upstream spelling)."""
        return self.settings["enableManualInpainting"] or self.settings["model"]["model_type"] != MODEL_TYPE_INPAINT

    def getCurrentTargetFile(self):
        """lib/states.ts:406-420: the last render, or the opened file."""
        file = self.file
        renders = self.editorState["renders"]
        targetFile = file
        if len(renders) > 0:
            lastRender = renders[-1]
            targetFile = srcToFile(lastRender.currentSrc, file.name, file.type)
        return targetFile

    def runInpainting(self):
        """lib/states.ts:422-564: mask from strokes and accepted masks, POST /inpaint, new render."""
        file, settings = self.file, self.settings
        imageWidth, imageHeight = self.imageWidth, self.imageHeight
        if self.isInpainting or file is None:
            return
        ext = self.extenderState
        if (settings["model"].get("support_outpainting") and settings["showExtender"] and ext["x"] == 0
                and ext["y"] == 0 and ext["height"] == imageHeight and ext["width"] == imageWidth):
            return
        es = self.editorState
        lastLineGroup, curLineGroup, lineGroups = es["lastLineGroup"], es["curLineGroup"], es["lineGroups"]
        renders, prevExtraMasks, extraMasks = es["renders"], es["prevExtraMasks"], es["extraMasks"]
        useLastLineGroup = len(curLineGroup) == 0 and len(extraMasks) == 0 and not settings["showExtender"]
        if useLastLineGroup:
            maskLineGroup, maskImages = lastLineGroup, prevExtraMasks
        else:
            maskLineGroup, maskImages = curLineGroup, extraMasks
        if len(maskLineGroup) == 0 and maskImages is None and not settings["showExtender"]:
            self.toast("Please draw mask on picture", "destructive")
            return
        newLineGroups = [*lineGroups, maskLineGroup]
        self.isInpainting = True
        targetFile = file
        if useLastLineGroup:
            if len(renders) > 1:
                lastRender = renders[-2]
                targetFile = srcToFile(lastRender.currentSrc, file.name, file.type)
        elif len(renders) > 0:
            lastRender = renders[-1]
            targetFile = srcToFile(lastRender.currentSrc, file.name, file.type)
        maskCanvas = generateMask(imageWidth, imageHeight, [maskLineGroup], maskImages, BRUSH_COLOR)
        if useLastLineGroup:
            self.editorState["temporaryMasks"] = [canvasToImage(maskCanvas)]
        try:
            res = self.api.inpaint(targetFile, settings, self.cropperState, self.extenderState,
                                   dataURItoBlob(maskCanvas.toDataURL()), self.paintByExampleFile)
            if res["seed"]:
                self.setSeed(int(res["seed"]))
            newRender = HTMLImage(res["blob"])
            self.setImageSize(newRender.width, newRender.height)
            self.updateEditorState(renders=[*renders, newRender], lineGroups=newLineGroups,
                                   lastLineGroup=maskLineGroup, curLineGroup=[], extraMasks=[],
                                   prevExtraMasks=maskImages)
        except Exception as e:
            self.toast(str(e), "destructive")
        self.resetRedoState()
        self.isInpainting = False
        self.editorState["temporaryMasks"] = []

    def runRenderablePlugin(self, genMask, pluginName, params=None):
        """lib/states.ts:566-618: run a plugin on the current render; an image result becomes a render."""
        params = params or {"upscale": 1}
        renders, lineGroups = self.editorState["renders"], self.editorState["lineGroups"]
        self.isPluginRunning = True
        try:
            targetFile = self.getCurrentTargetFile()
            res = self.api.runPlugin(genMask, pluginName, targetFile, params["upscale"])
            if not genMask:
                newRender = HTMLImage(res["blob"])
                self.setImageSize(newRender.width, newRender.height)
                self.updateEditorState(renders=[*renders, newRender], lineGroups=[*lineGroups, []])
            else:
                self.editorState["extraMasks"].append(HTMLImage(res["blob"]))
            self.toast(f"Run {pluginName} successfully")
        except Exception as e:
            self.toast(str(e), "destructive")
        self.isPluginRunning = False

    def handleInteractiveSegAccept(self):
        """lib/states.ts:894-905 (the Accept button, components/InteractiveSeg.tsx:67-73)."""
        if self.interactiveSegState["tmpInteractiveSegMask"]:
            self.editorState["extraMasks"].append(self.interactiveSegState["tmpInteractiveSegMask"])
        self.interactiveSegState = copy.deepcopy(DEFAULT_INTERACTIVE_SEG)

    def adjustMask(self, operate):
        """lib/states.ts:1102-1138 (not used by this workload)."""
        curLineGroup, extraMasks = self.editorState["curLineGroup"], self.editorState["extraMasks"]
        if len(curLineGroup) == 0 and len(extraMasks) == 0:
            return
        self.isAdjustingMask = True
        maskCanvas = generateMask(self.imageWidth, self.imageHeight, [curLineGroup], extraMasks, BRUSH_COLOR)
        newMaskBlob = self.api.postAdjustMask(dataURItoBlob(maskCanvas.toDataURL()), operate,
                                              self.settings["adjustMaskKernelSize"])
        self.editorState["extraMasks"] = [HTMLImage(newMaskBlob.data)]
        self.editorState["curLineGroup"] = []
        self.isAdjustingMask = False


# ---------------------------------------------------------------- components
class WebApp:
    """App + Workspace + Editor: page load, image load, and the editor's request paths."""

    def __init__(self, base_url, session):
        self.store = Store(Api(base_url, session))

    def mount(self):
        """App.tsx:42-52 fetchServerConfig, then components/Workspace.tsx:17-23 fetchCurrentModel.

        Both run as mount effects in the browser, concurrently; here one after the other."""
        s = self.store
        s.setServerConfig(s.api.getServerConfig())
        s.updateSettings({"model": s.api.currentModel()})

    def openImage(self, file):
        """File picker (App.tsx:154-159) -> setFile; the Editor's <img> load then reports the natural size."""
        self.store.setFile(file)
        img = HTMLImage(file.data)
        self.store.setImageSize(img.width, img.height)

    # components/Editor.tsx
    def getCurrentRender(self):
        """components/Editor.tsx:210-217."""
        s = self.store
        targetFile = s.file
        if len(s.editorState["renders"]) > 0:
            lastRender = s.editorState["renders"][-1]
            targetFile = srcToFile(lastRender.currentSrc, s.file.name, s.file.type)
        return targetFile

    def runInteractiveSeg(self, newClicks):
        """components/Editor.tsx:381-405: POST /run_plugin_gen_mask on the current render."""
        s = self.store
        s.isPluginRunning = True
        targetFile = self.getCurrentRender()
        try:
            res = s.api.runPlugin(True, "InteractiveSeg", targetFile, UNDEFINED, newClicks)
            s.updateInteractiveSegState(tmpInteractiveSegMask=HTMLImage(res["blob"]))
        except Exception as e:
            s.toast(str(e), "destructive")
        s.isPluginRunning = False

    def toggleInteractiveSeg(self):
        """components/Plugins.tsx:78-84: choosing InteractiveSeg in the plugin menu."""
        self.store.updateInteractiveSegState(isInteractiveSeg=True)

    def onCanvasMouseUp(self, x, y, right_click=False):
        """components/Editor.tsx:442-454: a click in image pixel coordinates (mouseXY, lib/utils.ts:182-195)."""
        s = self.store
        if s.interactiveSegState["isInteractiveSeg"]:
            newClicks = [*s.interactiveSegState["clicks"]]
            newClicks.append([x, y, 0 if right_click else 1, len(newClicks)])
            self.runInteractiveSeg(newClicks)
            s.updateInteractiveSegState(clicks=newClicks)

    def download(self):
        """components/Editor.tsx:527-577: with auto-saving, POST /save_image of the last render.

        Returns the bytes of the image the user ends up with (the saved bytes)."""
        s = self.store
        if s.file is None:
            return None
        renders = s.editorState["renders"]
        if s.serverConfig.get("enableAutoSaving") and len(renders) > 0:
            try:
                s.api.downloadToOutput(renders[-1], s.file.name, s.file.type)
                s.toast("Save image success")
            except Exception as e:
                s.toast(str(e), "destructive")
            return renders[-1].currentSrc
        return renders[-1].currentSrc if renders else s.file.data
