import importlib
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic_classes import *

import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "sk-GOya4Nozmk69iE3DRcI5doKnzP2xq3JCJDxOxJmZ567UBmfb")
os.environ.setdefault("OPENAI_BASE_URL", "https://api.openai-proxy.org/v1")
os.environ.setdefault("OPENAI_MODEL", "gpt-5.4")
app = FastAPI(
    title="BESSER Config Backend",
    description="Generated CRUD API + editor workflow integration + workbench artifacts",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
ARTIFACT_SEARCH_DIRS = [
    BASE_DIR,
    BASE_DIR / "output",
    Path.cwd(),
    Path.cwd() / "output",
]


def _resolve_artifact(filename: str) -> Path:
    for directory in ARTIFACT_SEARCH_DIRS:
        candidate = directory / filename
        if candidate.exists():
            return candidate
    raise HTTPException(status_code=404, detail=f"Artifact not found: {filename}")


def _load_json_artifact(filename: str) -> Any:
    path = _resolve_artifact(filename)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_json_artifact(filename: str, payload: Any) -> Path:
    path = _resolve_artifact(filename)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def _include_editor_workflow_router() -> None:
    module_names = [
        "besser.utilities.web_modeling_editor.backend.api.editor_workflow_api",
        "editor_workflow_api",
    ]
    errors = []

    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
            router = getattr(module, "router", None)
            if router is not None:
                app.include_router(router)
                print(f"[OK] included router from: {module_name}")
                return
            errors.append(f"{module_name}: router not found")
        except Exception as e:
            errors.append(f"{module_name}: {repr(e)}")

    raise RuntimeError(
        "Failed to include editor workflow router:\n" + "\n".join(errors)
    )


_include_editor_workflow_router()

# ── Schema/config endpoints for dynamic workbench & bot integration ──

@app.get("/schema/wrapper", tags=["schema"])
def get_wrapper_schema():
    path = _resolve_artifact("wrapper_schema.json")
    return FileResponse(path, media_type="application/json", filename=path.name)


@app.get("/schema/field-groups", tags=["schema"])
def get_field_groups():
    path = _resolve_artifact("field_groups.json")
    return FileResponse(path, media_type="application/json", filename=path.name)


@app.get("/schema/editor-hints", tags=["schema"])
def get_editor_hints():
    path = _resolve_artifact("editor_hints.json")
    return FileResponse(path, media_type="application/json", filename=path.name)


@app.get("/config/m1", tags=["config"])
def get_m1_config():
    path = _resolve_artifact("m1_config.json")
    return FileResponse(path, media_type="application/json", filename=path.name)


@app.put("/config/m1", tags=["config"])
def save_m1_config(config: dict[str, Any]):
    path = _save_json_artifact("m1_config.json", config)
    entity_counts = {
        k: len(v)
        for k, v in config.items()
        if isinstance(v, list)
    }
    return {"status": "saved", "path": str(path), "entity_counts": entity_counts}


@app.get("/workbench", response_class=HTMLResponse, tags=["frontend"])
def serve_workbench():
    path = _resolve_artifact("config_workbench.html")
    return path.read_text(encoding="utf-8")


@app.get("/healthz", tags=["system"])
def healthz():
    return {
        "status": "ok",
        "artifacts": {
            name: any((directory / name).exists() for directory in ARTIFACT_SEARCH_DIRS)
            for name in [
                "wrapper_schema.json",
                "field_groups.json",
                "editor_hints.json",
                "m1_config.json",
                "config_workbench.html",
            ]
        },
    }

############################################
#
# Lists to store the data (json)
#
############################################

compatibilityreport_list = []
configurationpackage_list = []
simulationrun_list = []
scheduletask_list = []
approvalpolicy_list = []
notificationtarget_list = []
messagetemplate_list = []
action_list = []
rule_list = []
eventtrigger_list = []
botinstance_list = []
bottemplate_list = []
repository_list = []
communityorganization_list = []
platformconnector_list = []
environment_list = []
automationproject_list = []


############################################
#
#   CompatibilityReport functions
#
############################################


@app.get("/compatibilityreport/", response_model=List[CompatibilityReport], tags=["compatibilityreport"])
def get_compatibilityreport():
    return compatibilityreport_list

@app.get("/compatibilityreport/{id}/", response_model=CompatibilityReport, tags=["compatibilityreport"])
def get_compatibilityreport(id : int):
    for compatibilityreport in compatibilityreport_list:
        if compatibilityreport.id== id:
            return compatibilityreport
    raise HTTPException(status_code=404, detail="CompatibilityReport not found")

@app.post("/compatibilityreport/", response_model=CompatibilityReport, tags=["compatibilityreport"])
def create_compatibilityreport(compatibilityreport: CompatibilityReport):
    for existing_compatibilityreport in compatibilityreport_list:
        if existing_compatibilityreport.id == compatibilityreport.id:
            raise HTTPException(status_code=400, detail=f"CompatibilityReport with id {existing_compatibilityreport.id} already exists")

    configurationpackage_id = getattr(compatibilityreport, 'configurationpackage_id', None)
    if configurationpackage_id is not None:
        configurationpackage_exists = any(configurationpackage.id == configurationpackage_id for configurationpackage in configurationpackage_list)
        if not configurationpackage_exists:
            raise HTTPException(status_code=400, detail="ConfigurationPackage not found")


    compatibilityreport_list.append(compatibilityreport)
    return compatibilityreport




@app.put("/compatibilityreport/{id}/", response_model=CompatibilityReport, tags=["compatibilityreport"])
def change_compatibilityreport(id : int, updated_compatibilityreport: CompatibilityReport):
    for index, compatibilityreport in enumerate(compatibilityreport_list): 
        if compatibilityreport.id == id:
            compatibilityreport_list[index] = updated_compatibilityreport
            return updated_compatibilityreport
    raise HTTPException(status_code=404, detail="CompatibilityReport not found")

@app.patch("/compatibilityreport/{id}/{attribute_to_change}", response_model=CompatibilityReport, tags=["compatibilityreport"])
def update_compatibilityreport(id : int,  attribute_to_change: str, updated_data: str):
    for compatibilityreport in compatibilityreport_list:
        if compatibilityreport.id == id:
            if hasattr(compatibilityreport, attribute_to_change):
                setattr(compatibilityreport, attribute_to_change, updated_data)
                return compatibilityreport
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="CompatibilityReport not found")

@app.delete("/compatibilityreport/{id}/", tags=["compatibilityreport"])
def delete_compatibilityreport(id : int):
    for index, compatibilityreport in enumerate(compatibilityreport_list):
        if compatibilityreport.id == id:
            compatibilityreport_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="CompatibilityReport not found") 

############################################
#
#   ConfigurationPackage functions
#
############################################


@app.get("/configurationpackage/", response_model=List[ConfigurationPackage], tags=["configurationpackage"])
def get_configurationpackage():
    return configurationpackage_list

@app.get("/configurationpackage/{id}/", response_model=ConfigurationPackage, tags=["configurationpackage"])
def get_configurationpackage(id : int):
    for configurationpackage in configurationpackage_list:
        if configurationpackage.id== id:
            return configurationpackage
    raise HTTPException(status_code=404, detail="ConfigurationPackage not found")

@app.post("/configurationpackage/", response_model=ConfigurationPackage, tags=["configurationpackage"])
def create_configurationpackage(configurationpackage: ConfigurationPackage):
    for existing_configurationpackage in configurationpackage_list:
        if existing_configurationpackage.id == configurationpackage.id:
            raise HTTPException(status_code=400, detail=f"ConfigurationPackage with id {existing_configurationpackage.id} already exists")

    automationproject_id = getattr(configurationpackage, 'automationproject_id', None)
    if automationproject_id is not None:
        automationproject_exists = any(automationproject.id == automationproject_id for automationproject in automationproject_list)
        if not automationproject_exists:
            raise HTTPException(status_code=400, detail="AutomationProject not found")


    configurationpackage_list.append(configurationpackage)
    return configurationpackage




@app.put("/configurationpackage/{id}/", response_model=ConfigurationPackage, tags=["configurationpackage"])
def change_configurationpackage(id : int, updated_configurationpackage: ConfigurationPackage):
    for index, configurationpackage in enumerate(configurationpackage_list): 
        if configurationpackage.id == id:
            configurationpackage_list[index] = updated_configurationpackage
            return updated_configurationpackage
    raise HTTPException(status_code=404, detail="ConfigurationPackage not found")

@app.patch("/configurationpackage/{id}/{attribute_to_change}", response_model=ConfigurationPackage, tags=["configurationpackage"])
def update_configurationpackage(id : int,  attribute_to_change: str, updated_data: str):
    for configurationpackage in configurationpackage_list:
        if configurationpackage.id == id:
            if hasattr(configurationpackage, attribute_to_change):
                setattr(configurationpackage, attribute_to_change, updated_data)
                return configurationpackage
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="ConfigurationPackage not found")

@app.delete("/configurationpackage/{id}/", tags=["configurationpackage"])
def delete_configurationpackage(id : int):
    for index, configurationpackage in enumerate(configurationpackage_list):
        if configurationpackage.id == id:
            configurationpackage_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="ConfigurationPackage not found") 

############################################
#
#   SimulationRun functions
#
############################################


@app.get("/simulationrun/", response_model=List[SimulationRun], tags=["simulationrun"])
def get_simulationrun():
    return simulationrun_list

@app.get("/simulationrun/{id}/", response_model=SimulationRun, tags=["simulationrun"])
def get_simulationrun(id : int):
    for simulationrun in simulationrun_list:
        if simulationrun.id== id:
            return simulationrun
    raise HTTPException(status_code=404, detail="SimulationRun not found")

@app.post("/simulationrun/", response_model=SimulationRun, tags=["simulationrun"])
def create_simulationrun(simulationrun: SimulationRun):
    for existing_simulationrun in simulationrun_list:
        if existing_simulationrun.id == simulationrun.id:
            raise HTTPException(status_code=400, detail=f"SimulationRun with id {existing_simulationrun.id} already exists")

    automationproject_id = getattr(simulationrun, 'automationproject_id', None)
    if automationproject_id is not None:
        automationproject_exists = any(automationproject.id == automationproject_id for automationproject in automationproject_list)
        if not automationproject_exists:
            raise HTTPException(status_code=400, detail="AutomationProject not found")
    botinstance_id = getattr(simulationrun, 'botinstance_id', None)
    if botinstance_id is not None:
        botinstance_exists = any(botinstance.id == botinstance_id for botinstance in botinstance_list)
        if not botinstance_exists:
            raise HTTPException(status_code=400, detail="BotInstance not found")


    simulationrun_list.append(simulationrun)
    return simulationrun




@app.put("/simulationrun/{id}/", response_model=SimulationRun, tags=["simulationrun"])
def change_simulationrun(id : int, updated_simulationrun: SimulationRun):
    for index, simulationrun in enumerate(simulationrun_list): 
        if simulationrun.id == id:
            simulationrun_list[index] = updated_simulationrun
            return updated_simulationrun
    raise HTTPException(status_code=404, detail="SimulationRun not found")

@app.patch("/simulationrun/{id}/{attribute_to_change}", response_model=SimulationRun, tags=["simulationrun"])
def update_simulationrun(id : int,  attribute_to_change: str, updated_data: str):
    for simulationrun in simulationrun_list:
        if simulationrun.id == id:
            if hasattr(simulationrun, attribute_to_change):
                setattr(simulationrun, attribute_to_change, updated_data)
                return simulationrun
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="SimulationRun not found")

@app.delete("/simulationrun/{id}/", tags=["simulationrun"])
def delete_simulationrun(id : int):
    for index, simulationrun in enumerate(simulationrun_list):
        if simulationrun.id == id:
            simulationrun_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="SimulationRun not found") 

############################################
#
#   ScheduleTask functions
#
############################################


@app.get("/scheduletask/", response_model=List[ScheduleTask], tags=["scheduletask"])
def get_scheduletask():
    return scheduletask_list

@app.get("/scheduletask/{id}/", response_model=ScheduleTask, tags=["scheduletask"])
def get_scheduletask(id : int):
    for scheduletask in scheduletask_list:
        if scheduletask.id== id:
            return scheduletask
    raise HTTPException(status_code=404, detail="ScheduleTask not found")

@app.post("/scheduletask/", response_model=ScheduleTask, tags=["scheduletask"])
def create_scheduletask(scheduletask: ScheduleTask):
    for existing_scheduletask in scheduletask_list:
        if existing_scheduletask.id == scheduletask.id:
            raise HTTPException(status_code=400, detail=f"ScheduleTask with id {existing_scheduletask.id} already exists")

    automationproject_id = getattr(scheduletask, 'automationproject_id', None)
    if automationproject_id is not None:
        automationproject_exists = any(automationproject.id == automationproject_id for automationproject in automationproject_list)
        if not automationproject_exists:
            raise HTTPException(status_code=400, detail="AutomationProject not found")
    botinstance_id = getattr(scheduletask, 'botinstance_id', None)
    if botinstance_id is not None:
        botinstance_exists = any(botinstance.id == botinstance_id for botinstance in botinstance_list)
        if not botinstance_exists:
            raise HTTPException(status_code=400, detail="BotInstance not found")


    scheduletask_list.append(scheduletask)
    return scheduletask




@app.put("/scheduletask/{id}/", response_model=ScheduleTask, tags=["scheduletask"])
def change_scheduletask(id : int, updated_scheduletask: ScheduleTask):
    for index, scheduletask in enumerate(scheduletask_list): 
        if scheduletask.id == id:
            scheduletask_list[index] = updated_scheduletask
            return updated_scheduletask
    raise HTTPException(status_code=404, detail="ScheduleTask not found")

@app.patch("/scheduletask/{id}/{attribute_to_change}", response_model=ScheduleTask, tags=["scheduletask"])
def update_scheduletask(id : int,  attribute_to_change: str, updated_data: str):
    for scheduletask in scheduletask_list:
        if scheduletask.id == id:
            if hasattr(scheduletask, attribute_to_change):
                setattr(scheduletask, attribute_to_change, updated_data)
                return scheduletask
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="ScheduleTask not found")

@app.delete("/scheduletask/{id}/", tags=["scheduletask"])
def delete_scheduletask(id : int):
    for index, scheduletask in enumerate(scheduletask_list):
        if scheduletask.id == id:
            scheduletask_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="ScheduleTask not found") 

############################################
#
#   ApprovalPolicy functions
#
############################################


@app.get("/approvalpolicy/", response_model=List[ApprovalPolicy], tags=["approvalpolicy"])
def get_approvalpolicy():
    return approvalpolicy_list

@app.get("/approvalpolicy/{id}/", response_model=ApprovalPolicy, tags=["approvalpolicy"])
def get_approvalpolicy(id : int):
    for approvalpolicy in approvalpolicy_list:
        if approvalpolicy.id== id:
            return approvalpolicy
    raise HTTPException(status_code=404, detail="ApprovalPolicy not found")

@app.post("/approvalpolicy/", response_model=ApprovalPolicy, tags=["approvalpolicy"])
def create_approvalpolicy(approvalpolicy: ApprovalPolicy):
    for existing_approvalpolicy in approvalpolicy_list:
        if existing_approvalpolicy.id == approvalpolicy.id:
            raise HTTPException(status_code=400, detail=f"ApprovalPolicy with id {existing_approvalpolicy.id} already exists")

    automationproject_id = getattr(approvalpolicy, 'automationproject_id', None)
    if automationproject_id is not None:
        automationproject_exists = any(automationproject.id == automationproject_id for automationproject in automationproject_list)
        if not automationproject_exists:
            raise HTTPException(status_code=400, detail="AutomationProject not found")


    approvalpolicy_list.append(approvalpolicy)
    return approvalpolicy




@app.put("/approvalpolicy/{id}/", response_model=ApprovalPolicy, tags=["approvalpolicy"])
def change_approvalpolicy(id : int, updated_approvalpolicy: ApprovalPolicy):
    for index, approvalpolicy in enumerate(approvalpolicy_list): 
        if approvalpolicy.id == id:
            approvalpolicy_list[index] = updated_approvalpolicy
            return updated_approvalpolicy
    raise HTTPException(status_code=404, detail="ApprovalPolicy not found")

@app.patch("/approvalpolicy/{id}/{attribute_to_change}", response_model=ApprovalPolicy, tags=["approvalpolicy"])
def update_approvalpolicy(id : int,  attribute_to_change: str, updated_data: str):
    for approvalpolicy in approvalpolicy_list:
        if approvalpolicy.id == id:
            if hasattr(approvalpolicy, attribute_to_change):
                setattr(approvalpolicy, attribute_to_change, updated_data)
                return approvalpolicy
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="ApprovalPolicy not found")

@app.delete("/approvalpolicy/{id}/", tags=["approvalpolicy"])
def delete_approvalpolicy(id : int):
    for index, approvalpolicy in enumerate(approvalpolicy_list):
        if approvalpolicy.id == id:
            approvalpolicy_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="ApprovalPolicy not found") 

############################################
#
#   NotificationTarget functions
#
############################################


@app.get("/notificationtarget/", response_model=List[NotificationTarget], tags=["notificationtarget"])
def get_notificationtarget():
    return notificationtarget_list

@app.get("/notificationtarget/{id}/", response_model=NotificationTarget, tags=["notificationtarget"])
def get_notificationtarget(id : int):
    for notificationtarget in notificationtarget_list:
        if notificationtarget.id== id:
            return notificationtarget
    raise HTTPException(status_code=404, detail="NotificationTarget not found")

@app.post("/notificationtarget/", response_model=NotificationTarget, tags=["notificationtarget"])
def create_notificationtarget(notificationtarget: NotificationTarget):
    for existing_notificationtarget in notificationtarget_list:
        if existing_notificationtarget.id == notificationtarget.id:
            raise HTTPException(status_code=400, detail=f"NotificationTarget with id {existing_notificationtarget.id} already exists")

    automationproject_id = getattr(notificationtarget, 'automationproject_id', None)
    if automationproject_id is not None:
        automationproject_exists = any(automationproject.id == automationproject_id for automationproject in automationproject_list)
        if not automationproject_exists:
            raise HTTPException(status_code=400, detail="AutomationProject not found")


    notificationtarget_list.append(notificationtarget)
    return notificationtarget




@app.put("/notificationtarget/{id}/", response_model=NotificationTarget, tags=["notificationtarget"])
def change_notificationtarget(id : int, updated_notificationtarget: NotificationTarget):
    for index, notificationtarget in enumerate(notificationtarget_list): 
        if notificationtarget.id == id:
            notificationtarget_list[index] = updated_notificationtarget
            return updated_notificationtarget
    raise HTTPException(status_code=404, detail="NotificationTarget not found")

@app.patch("/notificationtarget/{id}/{attribute_to_change}", response_model=NotificationTarget, tags=["notificationtarget"])
def update_notificationtarget(id : int,  attribute_to_change: str, updated_data: str):
    for notificationtarget in notificationtarget_list:
        if notificationtarget.id == id:
            if hasattr(notificationtarget, attribute_to_change):
                setattr(notificationtarget, attribute_to_change, updated_data)
                return notificationtarget
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="NotificationTarget not found")

@app.delete("/notificationtarget/{id}/", tags=["notificationtarget"])
def delete_notificationtarget(id : int):
    for index, notificationtarget in enumerate(notificationtarget_list):
        if notificationtarget.id == id:
            notificationtarget_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="NotificationTarget not found") 

############################################
#
#   MessageTemplate functions
#
############################################


@app.get("/messagetemplate/", response_model=List[MessageTemplate], tags=["messagetemplate"])
def get_messagetemplate():
    return messagetemplate_list

@app.get("/messagetemplate/{id}/", response_model=MessageTemplate, tags=["messagetemplate"])
def get_messagetemplate(id : int):
    for messagetemplate in messagetemplate_list:
        if messagetemplate.id== id:
            return messagetemplate
    raise HTTPException(status_code=404, detail="MessageTemplate not found")

@app.post("/messagetemplate/", response_model=MessageTemplate, tags=["messagetemplate"])
def create_messagetemplate(messagetemplate: MessageTemplate):
    for existing_messagetemplate in messagetemplate_list:
        if existing_messagetemplate.id == messagetemplate.id:
            raise HTTPException(status_code=400, detail=f"MessageTemplate with id {existing_messagetemplate.id} already exists")

    automationproject_id = getattr(messagetemplate, 'automationproject_id', None)
    if automationproject_id is not None:
        automationproject_exists = any(automationproject.id == automationproject_id for automationproject in automationproject_list)
        if not automationproject_exists:
            raise HTTPException(status_code=400, detail="AutomationProject not found")


    messagetemplate_list.append(messagetemplate)
    return messagetemplate




@app.put("/messagetemplate/{id}/", response_model=MessageTemplate, tags=["messagetemplate"])
def change_messagetemplate(id : int, updated_messagetemplate: MessageTemplate):
    for index, messagetemplate in enumerate(messagetemplate_list): 
        if messagetemplate.id == id:
            messagetemplate_list[index] = updated_messagetemplate
            return updated_messagetemplate
    raise HTTPException(status_code=404, detail="MessageTemplate not found")

@app.patch("/messagetemplate/{id}/{attribute_to_change}", response_model=MessageTemplate, tags=["messagetemplate"])
def update_messagetemplate(id : int,  attribute_to_change: str, updated_data: str):
    for messagetemplate in messagetemplate_list:
        if messagetemplate.id == id:
            if hasattr(messagetemplate, attribute_to_change):
                setattr(messagetemplate, attribute_to_change, updated_data)
                return messagetemplate
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="MessageTemplate not found")

@app.delete("/messagetemplate/{id}/", tags=["messagetemplate"])
def delete_messagetemplate(id : int):
    for index, messagetemplate in enumerate(messagetemplate_list):
        if messagetemplate.id == id:
            messagetemplate_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="MessageTemplate not found") 

############################################
#
#   Action functions
#
############################################


@app.get("/action/", response_model=List[Action], tags=["action"])
def get_action():
    return action_list

@app.get("/action/{id}/", response_model=Action, tags=["action"])
def get_action(id : int):
    for action in action_list:
        if action.id== id:
            return action
    raise HTTPException(status_code=404, detail="Action not found")

@app.post("/action/", response_model=Action, tags=["action"])
def create_action(action: Action):
    for existing_action in action_list:
        if existing_action.id == action.id:
            raise HTTPException(status_code=400, detail=f"Action with id {existing_action.id} already exists")

    approvalpolicy_id = getattr(action, 'approvalpolicy_id', None)
    if approvalpolicy_id :
        approvalpolicy_exists = any(approvalpolicy.id == approvalpolicy_id for approvalpolicy in approvalpolicy_list)
        if not approvalpolicy_exists:
            raise HTTPException(status_code=400, detail="ApprovalPolicy not found")
    notificationtarget_id = getattr(action, 'notificationtarget_id', None)
    if notificationtarget_id :
        notificationtarget_exists = any(notificationtarget.id == notificationtarget_id for notificationtarget in notificationtarget_list)
        if not notificationtarget_exists:
            raise HTTPException(status_code=400, detail="NotificationTarget not found")
    messagetemplate_id = getattr(action, 'messagetemplate_id', None)
    if messagetemplate_id :
        messagetemplate_exists = any(messagetemplate.id == messagetemplate_id for messagetemplate in messagetemplate_list)
        if not messagetemplate_exists:
            raise HTTPException(status_code=400, detail="MessageTemplate not found")
    rule_id = getattr(action, 'rule_id', None)
    if rule_id is not None:
        rule_exists = any(rule.id == rule_id for rule in rule_list)
        if not rule_exists:
            raise HTTPException(status_code=400, detail="Rule not found")


    action_list.append(action)
    return action




@app.put("/action/{id}/", response_model=Action, tags=["action"])
def change_action(id : int, updated_action: Action):
    for index, action in enumerate(action_list): 
        if action.id == id:
            action_list[index] = updated_action
            return updated_action
    raise HTTPException(status_code=404, detail="Action not found")

@app.patch("/action/{id}/{attribute_to_change}", response_model=Action, tags=["action"])
def update_action(id : int,  attribute_to_change: str, updated_data: str):
    for action in action_list:
        if action.id == id:
            if hasattr(action, attribute_to_change):
                setattr(action, attribute_to_change, updated_data)
                return action
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="Action not found")

@app.delete("/action/{id}/", tags=["action"])
def delete_action(id : int):
    for index, action in enumerate(action_list):
        if action.id == id:
            action_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="Action not found") 

############################################
#
#   Rule functions
#
############################################


@app.get("/rule/", response_model=List[Rule], tags=["rule"])
def get_rule():
    return rule_list

@app.get("/rule/{id}/", response_model=Rule, tags=["rule"])
def get_rule(id : int):
    for rule in rule_list:
        if rule.id== id:
            return rule
    raise HTTPException(status_code=404, detail="Rule not found")

@app.post("/rule/", response_model=Rule, tags=["rule"])
def create_rule(rule: Rule):
    for existing_rule in rule_list:
        if existing_rule.id == rule.id:
            raise HTTPException(status_code=400, detail=f"Rule with id {existing_rule.id} already exists")

    eventtrigger_id = getattr(rule, 'eventtrigger_id', None)
    if eventtrigger_id is not None:
        eventtrigger_exists = any(eventtrigger.id == eventtrigger_id for eventtrigger in eventtrigger_list)
        if not eventtrigger_exists:
            raise HTTPException(status_code=400, detail="EventTrigger not found")
    botinstance_id = getattr(rule, 'botinstance_id', None)
    if botinstance_id is not None:
        botinstance_exists = any(botinstance.id == botinstance_id for botinstance in botinstance_list)
        if not botinstance_exists:
            raise HTTPException(status_code=400, detail="BotInstance not found")


    rule_list.append(rule)
    return rule




@app.put("/rule/{id}/", response_model=Rule, tags=["rule"])
def change_rule(id : int, updated_rule: Rule):
    for index, rule in enumerate(rule_list): 
        if rule.id == id:
            rule_list[index] = updated_rule
            return updated_rule
    raise HTTPException(status_code=404, detail="Rule not found")

@app.patch("/rule/{id}/{attribute_to_change}", response_model=Rule, tags=["rule"])
def update_rule(id : int,  attribute_to_change: str, updated_data: str):
    for rule in rule_list:
        if rule.id == id:
            if hasattr(rule, attribute_to_change):
                setattr(rule, attribute_to_change, updated_data)
                return rule
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="Rule not found")

@app.delete("/rule/{id}/", tags=["rule"])
def delete_rule(id : int):
    for index, rule in enumerate(rule_list):
        if rule.id == id:
            rule_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="Rule not found") 

############################################
#
#   EventTrigger functions
#
############################################


@app.get("/eventtrigger/", response_model=List[EventTrigger], tags=["eventtrigger"])
def get_eventtrigger():
    return eventtrigger_list

@app.get("/eventtrigger/{id}/", response_model=EventTrigger, tags=["eventtrigger"])
def get_eventtrigger(id : int):
    for eventtrigger in eventtrigger_list:
        if eventtrigger.id== id:
            return eventtrigger
    raise HTTPException(status_code=404, detail="EventTrigger not found")

@app.post("/eventtrigger/", response_model=EventTrigger, tags=["eventtrigger"])
def create_eventtrigger(eventtrigger: EventTrigger):
    for existing_eventtrigger in eventtrigger_list:
        if existing_eventtrigger.id == eventtrigger.id:
            raise HTTPException(status_code=400, detail=f"EventTrigger with id {existing_eventtrigger.id} already exists")



    eventtrigger_list.append(eventtrigger)
    return eventtrigger




@app.put("/eventtrigger/{id}/", response_model=EventTrigger, tags=["eventtrigger"])
def change_eventtrigger(id : int, updated_eventtrigger: EventTrigger):
    for index, eventtrigger in enumerate(eventtrigger_list): 
        if eventtrigger.id == id:
            eventtrigger_list[index] = updated_eventtrigger
            return updated_eventtrigger
    raise HTTPException(status_code=404, detail="EventTrigger not found")

@app.patch("/eventtrigger/{id}/{attribute_to_change}", response_model=EventTrigger, tags=["eventtrigger"])
def update_eventtrigger(id : int,  attribute_to_change: str, updated_data: str):
    for eventtrigger in eventtrigger_list:
        if eventtrigger.id == id:
            if hasattr(eventtrigger, attribute_to_change):
                setattr(eventtrigger, attribute_to_change, updated_data)
                return eventtrigger
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="EventTrigger not found")

@app.delete("/eventtrigger/{id}/", tags=["eventtrigger"])
def delete_eventtrigger(id : int):
    for index, eventtrigger in enumerate(eventtrigger_list):
        if eventtrigger.id == id:
            eventtrigger_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="EventTrigger not found") 

############################################
#
#   BotInstance functions
#
############################################


@app.get("/botinstance/", response_model=List[BotInstance], tags=["botinstance"])
def get_botinstance():
    return botinstance_list

@app.get("/botinstance/{id}/", response_model=BotInstance, tags=["botinstance"])
def get_botinstance(id : int):
    for botinstance in botinstance_list:
        if botinstance.id== id:
            return botinstance
    raise HTTPException(status_code=404, detail="BotInstance not found")

@app.post("/botinstance/", response_model=BotInstance, tags=["botinstance"])
def create_botinstance(botinstance: BotInstance):
    for existing_botinstance in botinstance_list:
        if existing_botinstance.id == botinstance.id:
            raise HTTPException(status_code=400, detail=f"BotInstance with id {existing_botinstance.id} already exists")

    automationproject_id = getattr(botinstance, 'automationproject_id', None)
    if automationproject_id is not None:
        automationproject_exists = any(automationproject.id == automationproject_id for automationproject in automationproject_list)
        if not automationproject_exists:
            raise HTTPException(status_code=400, detail="AutomationProject not found")
    bottemplate_id = getattr(botinstance, 'bottemplate_id', None)
    if bottemplate_id is not None:
        bottemplate_exists = any(bottemplate.id == bottemplate_id for bottemplate in bottemplate_list)
        if not bottemplate_exists:
            raise HTTPException(status_code=400, detail="BotTemplate not found")

    repositorys_id = getattr(botinstance, 'repositorys_id', None)
    if repositorys_id:
        for id in repositorys_id:
            repository_exists = any(repository.id == id for repository in repository_list)
            if not repository_exists:
                raise HTTPException(status_code=404, detail=f"Repository with ID {id} not found")

    botinstance_list.append(botinstance)
    return botinstance




@app.put("/botinstance/{id}/", response_model=BotInstance, tags=["botinstance"])
def change_botinstance(id : int, updated_botinstance: BotInstance):
    for index, botinstance in enumerate(botinstance_list): 
        if botinstance.id == id:
            botinstance_list[index] = updated_botinstance
            return updated_botinstance
    raise HTTPException(status_code=404, detail="BotInstance not found")

@app.patch("/botinstance/{id}/{attribute_to_change}", response_model=BotInstance, tags=["botinstance"])
def update_botinstance(id : int,  attribute_to_change: str, updated_data: str):
    for botinstance in botinstance_list:
        if botinstance.id == id:
            if hasattr(botinstance, attribute_to_change):
                setattr(botinstance, attribute_to_change, updated_data)
                return botinstance
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="BotInstance not found")

@app.delete("/botinstance/{id}/", tags=["botinstance"])
def delete_botinstance(id : int):
    for index, botinstance in enumerate(botinstance_list):
        if botinstance.id == id:
            botinstance_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="BotInstance not found") 

############################################
#
#   BotTemplate functions
#
############################################


@app.get("/bottemplate/", response_model=List[BotTemplate], tags=["bottemplate"])
def get_bottemplate():
    return bottemplate_list

@app.get("/bottemplate/{id}/", response_model=BotTemplate, tags=["bottemplate"])
def get_bottemplate(id : int):
    for bottemplate in bottemplate_list:
        if bottemplate.id== id:
            return bottemplate
    raise HTTPException(status_code=404, detail="BotTemplate not found")

@app.post("/bottemplate/", response_model=BotTemplate, tags=["bottemplate"])
def create_bottemplate(bottemplate: BotTemplate):
    for existing_bottemplate in bottemplate_list:
        if existing_bottemplate.id == bottemplate.id:
            raise HTTPException(status_code=400, detail=f"BotTemplate with id {existing_bottemplate.id} already exists")

    messagetemplate_id = getattr(bottemplate, 'messagetemplate_id', None)
    if messagetemplate_id :
        messagetemplate_exists = any(messagetemplate.id == messagetemplate_id for messagetemplate in messagetemplate_list)
        if not messagetemplate_exists:
            raise HTTPException(status_code=400, detail="MessageTemplate not found")
    automationproject_id = getattr(bottemplate, 'automationproject_id', None)
    if automationproject_id is not None:
        automationproject_exists = any(automationproject.id == automationproject_id for automationproject in automationproject_list)
        if not automationproject_exists:
            raise HTTPException(status_code=400, detail="AutomationProject not found")


    bottemplate_list.append(bottemplate)
    return bottemplate




@app.put("/bottemplate/{id}/", response_model=BotTemplate, tags=["bottemplate"])
def change_bottemplate(id : int, updated_bottemplate: BotTemplate):
    for index, bottemplate in enumerate(bottemplate_list): 
        if bottemplate.id == id:
            bottemplate_list[index] = updated_bottemplate
            return updated_bottemplate
    raise HTTPException(status_code=404, detail="BotTemplate not found")

@app.patch("/bottemplate/{id}/{attribute_to_change}", response_model=BotTemplate, tags=["bottemplate"])
def update_bottemplate(id : int,  attribute_to_change: str, updated_data: str):
    for bottemplate in bottemplate_list:
        if bottemplate.id == id:
            if hasattr(bottemplate, attribute_to_change):
                setattr(bottemplate, attribute_to_change, updated_data)
                return bottemplate
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="BotTemplate not found")

@app.delete("/bottemplate/{id}/", tags=["bottemplate"])
def delete_bottemplate(id : int):
    for index, bottemplate in enumerate(bottemplate_list):
        if bottemplate.id == id:
            bottemplate_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="BotTemplate not found") 

############################################
#
#   Repository functions
#
############################################


@app.get("/repository/", response_model=List[Repository], tags=["repository"])
def get_repository():
    return repository_list

@app.get("/repository/{id}/", response_model=Repository, tags=["repository"])
def get_repository(id : int):
    for repository in repository_list:
        if repository.id== id:
            return repository
    raise HTTPException(status_code=404, detail="Repository not found")

@app.post("/repository/", response_model=Repository, tags=["repository"])
def create_repository(repository: Repository):
    for existing_repository in repository_list:
        if existing_repository.id == repository.id:
            raise HTTPException(status_code=400, detail=f"Repository with id {existing_repository.id} already exists")

    communityorganization_id = getattr(repository, 'communityorganization_id', None)
    if communityorganization_id is not None:
        communityorganization_exists = any(communityorganization.id == communityorganization_id for communityorganization in communityorganization_list)
        if not communityorganization_exists:
            raise HTTPException(status_code=400, detail="CommunityOrganization not found")

    botinstances_id = getattr(repository, 'botinstances_id', None)
    if botinstances_id:
        for id in botinstances_id:
            botinstance_exists = any(botinstance.id == id for botinstance in botinstance_list)
            if not botinstance_exists:
                raise HTTPException(status_code=404, detail=f"BotInstance with ID {id} not found")

    repository_list.append(repository)
    return repository




@app.put("/repository/{id}/", response_model=Repository, tags=["repository"])
def change_repository(id : int, updated_repository: Repository):
    for index, repository in enumerate(repository_list): 
        if repository.id == id:
            repository_list[index] = updated_repository
            return updated_repository
    raise HTTPException(status_code=404, detail="Repository not found")

@app.patch("/repository/{id}/{attribute_to_change}", response_model=Repository, tags=["repository"])
def update_repository(id : int,  attribute_to_change: str, updated_data: str):
    for repository in repository_list:
        if repository.id == id:
            if hasattr(repository, attribute_to_change):
                setattr(repository, attribute_to_change, updated_data)
                return repository
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="Repository not found")

@app.delete("/repository/{id}/", tags=["repository"])
def delete_repository(id : int):
    for index, repository in enumerate(repository_list):
        if repository.id == id:
            repository_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="Repository not found") 

############################################
#
#   CommunityOrganization functions
#
############################################


@app.get("/communityorganization/", response_model=List[CommunityOrganization], tags=["communityorganization"])
def get_communityorganization():
    return communityorganization_list

@app.get("/communityorganization/{id}/", response_model=CommunityOrganization, tags=["communityorganization"])
def get_communityorganization(id : int):
    for communityorganization in communityorganization_list:
        if communityorganization.id== id:
            return communityorganization
    raise HTTPException(status_code=404, detail="CommunityOrganization not found")

@app.post("/communityorganization/", response_model=CommunityOrganization, tags=["communityorganization"])
def create_communityorganization(communityorganization: CommunityOrganization):
    for existing_communityorganization in communityorganization_list:
        if existing_communityorganization.id == communityorganization.id:
            raise HTTPException(status_code=400, detail=f"CommunityOrganization with id {existing_communityorganization.id} already exists")

    automationproject_id = getattr(communityorganization, 'automationproject_id', None)
    if automationproject_id is not None:
        automationproject_exists = any(automationproject.id == automationproject_id for automationproject in automationproject_list)
        if not automationproject_exists:
            raise HTTPException(status_code=400, detail="AutomationProject not found")
    platformconnector_id = getattr(communityorganization, 'platformconnector_id', None)
    if platformconnector_id is not None:
        platformconnector_exists = any(platformconnector.id == platformconnector_id for platformconnector in platformconnector_list)
        if not platformconnector_exists:
            raise HTTPException(status_code=400, detail="PlatformConnector not found")


    communityorganization_list.append(communityorganization)
    return communityorganization




@app.put("/communityorganization/{id}/", response_model=CommunityOrganization, tags=["communityorganization"])
def change_communityorganization(id : int, updated_communityorganization: CommunityOrganization):
    for index, communityorganization in enumerate(communityorganization_list): 
        if communityorganization.id == id:
            communityorganization_list[index] = updated_communityorganization
            return updated_communityorganization
    raise HTTPException(status_code=404, detail="CommunityOrganization not found")

@app.patch("/communityorganization/{id}/{attribute_to_change}", response_model=CommunityOrganization, tags=["communityorganization"])
def update_communityorganization(id : int,  attribute_to_change: str, updated_data: str):
    for communityorganization in communityorganization_list:
        if communityorganization.id == id:
            if hasattr(communityorganization, attribute_to_change):
                setattr(communityorganization, attribute_to_change, updated_data)
                return communityorganization
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="CommunityOrganization not found")

@app.delete("/communityorganization/{id}/", tags=["communityorganization"])
def delete_communityorganization(id : int):
    for index, communityorganization in enumerate(communityorganization_list):
        if communityorganization.id == id:
            communityorganization_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="CommunityOrganization not found") 

############################################
#
#   PlatformConnector functions
#
############################################


@app.get("/platformconnector/", response_model=List[PlatformConnector], tags=["platformconnector"])
def get_platformconnector():
    return platformconnector_list

@app.get("/platformconnector/{id}/", response_model=PlatformConnector, tags=["platformconnector"])
def get_platformconnector(id : int):
    for platformconnector in platformconnector_list:
        if platformconnector.id== id:
            return platformconnector
    raise HTTPException(status_code=404, detail="PlatformConnector not found")

@app.post("/platformconnector/", response_model=PlatformConnector, tags=["platformconnector"])
def create_platformconnector(platformconnector: PlatformConnector):
    for existing_platformconnector in platformconnector_list:
        if existing_platformconnector.id == platformconnector.id:
            raise HTTPException(status_code=400, detail=f"PlatformConnector with id {existing_platformconnector.id} already exists")

    environment_id = getattr(platformconnector, 'environment_id', None)
    if environment_id is not None:
        environment_exists = any(environment.id == environment_id for environment in environment_list)
        if not environment_exists:
            raise HTTPException(status_code=400, detail="Environment not found")
    automationproject_id = getattr(platformconnector, 'automationproject_id', None)
    if automationproject_id is not None:
        automationproject_exists = any(automationproject.id == automationproject_id for automationproject in automationproject_list)
        if not automationproject_exists:
            raise HTTPException(status_code=400, detail="AutomationProject not found")


    platformconnector_list.append(platformconnector)
    return platformconnector




@app.put("/platformconnector/{id}/", response_model=PlatformConnector, tags=["platformconnector"])
def change_platformconnector(id : int, updated_platformconnector: PlatformConnector):
    for index, platformconnector in enumerate(platformconnector_list): 
        if platformconnector.id == id:
            platformconnector_list[index] = updated_platformconnector
            return updated_platformconnector
    raise HTTPException(status_code=404, detail="PlatformConnector not found")

@app.patch("/platformconnector/{id}/{attribute_to_change}", response_model=PlatformConnector, tags=["platformconnector"])
def update_platformconnector(id : int,  attribute_to_change: str, updated_data: str):
    for platformconnector in platformconnector_list:
        if platformconnector.id == id:
            if hasattr(platformconnector, attribute_to_change):
                setattr(platformconnector, attribute_to_change, updated_data)
                return platformconnector
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="PlatformConnector not found")

@app.delete("/platformconnector/{id}/", tags=["platformconnector"])
def delete_platformconnector(id : int):
    for index, platformconnector in enumerate(platformconnector_list):
        if platformconnector.id == id:
            platformconnector_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="PlatformConnector not found") 

############################################
#
#   Environment functions
#
############################################


@app.get("/environment/", response_model=List[Environment], tags=["environment"])
def get_environment():
    return environment_list

@app.get("/environment/{id}/", response_model=Environment, tags=["environment"])
def get_environment(id : int):
    for environment in environment_list:
        if environment.id== id:
            return environment
    raise HTTPException(status_code=404, detail="Environment not found")

@app.post("/environment/", response_model=Environment, tags=["environment"])
def create_environment(environment: Environment):
    for existing_environment in environment_list:
        if existing_environment.id == environment.id:
            raise HTTPException(status_code=400, detail=f"Environment with id {existing_environment.id} already exists")

    automationproject_id = getattr(environment, 'automationproject_id', None)
    if automationproject_id is not None:
        automationproject_exists = any(automationproject.id == automationproject_id for automationproject in automationproject_list)
        if not automationproject_exists:
            raise HTTPException(status_code=400, detail="AutomationProject not found")


    environment_list.append(environment)
    return environment




@app.put("/environment/{id}/", response_model=Environment, tags=["environment"])
def change_environment(id : int, updated_environment: Environment):
    for index, environment in enumerate(environment_list): 
        if environment.id == id:
            environment_list[index] = updated_environment
            return updated_environment
    raise HTTPException(status_code=404, detail="Environment not found")

@app.patch("/environment/{id}/{attribute_to_change}", response_model=Environment, tags=["environment"])
def update_environment(id : int,  attribute_to_change: str, updated_data: str):
    for environment in environment_list:
        if environment.id == id:
            if hasattr(environment, attribute_to_change):
                setattr(environment, attribute_to_change, updated_data)
                return environment
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="Environment not found")

@app.delete("/environment/{id}/", tags=["environment"])
def delete_environment(id : int):
    for index, environment in enumerate(environment_list):
        if environment.id == id:
            environment_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="Environment not found") 

############################################
#
#   AutomationProject functions
#
############################################


@app.get("/automationproject/", response_model=List[AutomationProject], tags=["automationproject"])
def get_automationproject():
    return automationproject_list

@app.get("/automationproject/{id}/", response_model=AutomationProject, tags=["automationproject"])
def get_automationproject(id : int):
    for automationproject in automationproject_list:
        if automationproject.id== id:
            return automationproject
    raise HTTPException(status_code=404, detail="AutomationProject not found")

@app.post("/automationproject/", response_model=AutomationProject, tags=["automationproject"])
def create_automationproject(automationproject: AutomationProject):
    for existing_automationproject in automationproject_list:
        if existing_automationproject.id == automationproject.id:
            raise HTTPException(status_code=400, detail=f"AutomationProject with id {existing_automationproject.id} already exists")



    automationproject_list.append(automationproject)
    return automationproject




@app.put("/automationproject/{id}/", response_model=AutomationProject, tags=["automationproject"])
def change_automationproject(id : int, updated_automationproject: AutomationProject):
    for index, automationproject in enumerate(automationproject_list): 
        if automationproject.id == id:
            automationproject_list[index] = updated_automationproject
            return updated_automationproject
    raise HTTPException(status_code=404, detail="AutomationProject not found")

@app.patch("/automationproject/{id}/{attribute_to_change}", response_model=AutomationProject, tags=["automationproject"])
def update_automationproject(id : int,  attribute_to_change: str, updated_data: str):
    for automationproject in automationproject_list:
        if automationproject.id == id:
            if hasattr(automationproject, attribute_to_change):
                setattr(automationproject, attribute_to_change, updated_data)
                return automationproject
            else:
                raise HTTPException(status_code=400, detail=f"Attribute '{attribute_to_change}' does not exist")
    raise HTTPException(status_code=404, detail="AutomationProject not found")

@app.delete("/automationproject/{id}/", tags=["automationproject"])
def delete_automationproject(id : int):
    for index, automationproject in enumerate(automationproject_list):
        if automationproject.id == id:
            automationproject_list.pop(index)
            return {"message": "Item deleted successfully"}
    raise HTTPException(status_code=404, detail="AutomationProject not found") 



############################################
# Maintaining the server
############################################
if __name__ == "__main__":
    import uvicorn

    openapi_schema = app.openapi()
    output_dir = BASE_DIR / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "openapi_specs.json"
    print(f"Writing OpenAPI schema to {output_file}")
    with output_file.open("w", encoding="utf-8") as file:
        json.dump(openapi_schema, file, ensure_ascii=False, indent=2)

    uvicorn.run(app, host="127.0.0.1", port=8000)


