"""
图谱相关API路由
采用项目上下文机制，服务端持久化状态
"""

import os
import threading
import traceback

from flask import jsonify, request

from ..config import Config
from ..models.project import ProjectManager, ProjectStatus
from ..models.task import TaskManager, TaskStatus
from ..services.graph_builder import GraphBuilderService
from ..services.ontology_generator import OntologyGenerator
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.locale import get_locale, set_locale, t
from ..utils.logger import get_logger
from . import graph_bp

# 获取日志器
logger = get_logger("mirofish.api")


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    if not filename or "." not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext in Config.ALLOWED_EXTENSIONS


# ============== 项目管理接口 ==============


@graph_bp.route("/project/<project_id>", methods=["GET"])
def get_project(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        return jsonify({"success": False, "error": t("api.projectNotFound", id=project_id)}), 404
    return jsonify({"success": True, "data": project.to_dict()})


@graph_bp.route("/project/list", methods=["GET"])
def list_projects():
    limit = request.args.get("limit", 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    return jsonify(
        {"success": True, "data": [p.to_dict() for p in projects], "count": len(projects)}
    )


@graph_bp.route("/project/<project_id>", methods=["DELETE"])
def delete_project(project_id: str):
    success = ProjectManager.delete_project(project_id)
    if not success:
        return jsonify(
            {"success": False, "error": t("api.projectDeleteFailed", id=project_id)}
        ), 404
    return jsonify({"success": True, "message": t("api.projectDeleted", id=project_id)})


@graph_bp.route("/project/<project_id>/reset", methods=["POST"])
def reset_project(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        return jsonify({"success": False, "error": t("api.projectNotFound", id=project_id)}), 404
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)
    return jsonify(
        {
            "success": True,
            "message": t("api.projectReset", id=project_id),
            "data": project.to_dict(),
        }
    )


# ============== 接口1：上传文件并生成本体（原始multipart版本）==============


@graph_bp.route("/ontology/generate", methods=["POST"])
def generate_ontology():
    """
    接口1：上传文件，分析生成本体定义（multipart/form-data）
    """
    try:
        logger.info("=== 开始生成本体定义 ===")
        simulation_requirement = request.form.get("simulation_requirement", "")
        project_name = request.form.get("project_name", "Unnamed Project")
        additional_context = request.form.get("additional_context", "")

        if not simulation_requirement:
            return jsonify({"success": False, "error": t("api.requireSimulationRequirement")}), 400

        uploaded_files = request.files.getlist("files")
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({"success": False, "error": t("api.requireFileUpload")}), 400

        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        document_texts = []
        all_text = ""

        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                file_info = ProjectManager.save_file_to_project(
                    project.project_id, file, file.filename
                )
                project.files.append(
                    {"filename": file_info["original_filename"], "size": file_info["size"]}
                )
                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"

        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({"success": False, "error": t("api.noDocProcessed")}), 400

        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)

        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None,
        )

        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", []),
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)

        return jsonify(
            {
                "success": True,
                "data": {
                    "project_id": project.project_id,
                    "project_name": project.name,
                    "ontology": project.ontology,
                    "analysis_summary": project.analysis_summary,
                    "files": project.files,
                    "total_text_length": project.total_text_length,
                },
            }
        )
    except Exception as e:
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


# ============== 接口1b：JSON文本版本（供MCP/API客户端使用）==============


@graph_bp.route("/ontology/generate_from_text", methods=["POST"])
def generate_ontology_from_text():
    """
    Text-based version of generate_ontology for API/MCP clients that cannot upload files.

    Request (JSON):
        {
            "content": "text content to analyse",
            "simulation_requirement": "what to simulate or predict",
            "project_name": "optional project name",
            "additional_context": "optional extra context"
        }

    Returns:
        { "success": true, "data": { "project_id": "...", "ontology": {...}, "analysis_summary": "..." } }
    """
    try:
        logger.info("=== Starting ontology generation from text ===")

        data = request.get_json() or {}
        content = data.get("content", "")
        simulation_requirement = data.get("simulation_requirement", "")
        project_name = data.get("project_name", "Unnamed Project")
        additional_context = data.get("additional_context", "")

        if not simulation_requirement:
            return jsonify({"success": False, "error": "simulation_requirement is required"}), 400

        if not content:
            return jsonify({"success": False, "error": "content is required"}), 400

        # Create project
        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        logger.info(f"Created project: {project.project_id}")

        # Process text
        text = TextProcessor.preprocess_text(content)
        project.total_text_length = len(text)
        ProjectManager.save_extracted_text(project.project_id, text)
        project.files = [{"filename": "text_input.txt", "size": len(text)}]

        # Generate ontology
        logger.info("Calling LLM to generate ontology...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=[text],
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None,
        )

        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(f"Ontology generated: {entity_count} entity types, {edge_count} edge types")

        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", []),
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)

        logger.info(f"=== Ontology complete === project_id: {project.project_id}")

        return jsonify(
            {
                "success": True,
                "data": {
                    "project_id": project.project_id,
                    "project_name": project.name,
                    "ontology": project.ontology,
                    "analysis_summary": project.analysis_summary,
                    "total_text_length": project.total_text_length,
                },
            }
        )

    except Exception as e:
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


# ============== 接口2：构建图谱 ==============


@graph_bp.route("/build", methods=["POST"])
def build_graph():
    """
    接口2：根据project_id构建图谱
    """
    try:
        logger.info("=== 开始构建图谱 ===")

        errors = []
        if not Config.ZEP_API_KEY:
            errors.append(t("api.zepApiKeyMissing"))
        if errors:
            return jsonify(
                {"success": False, "error": t("api.configError", details="; ".join(errors))}
            ), 500

        data = request.get_json() or {}
        project_id = data.get("project_id")

        if not project_id:
            return jsonify({"success": False, "error": t("api.requireProjectId")}), 400

        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify(
                {"success": False, "error": t("api.projectNotFound", id=project_id)}
            ), 404

        force = data.get("force", False)

        if project.status == ProjectStatus.CREATED:
            return jsonify({"success": False, "error": t("api.ontologyNotGenerated")}), 400

        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify(
                {
                    "success": False,
                    "error": t("api.graphBuilding"),
                    "task_id": project.graph_build_task_id,
                }
            ), 400

        if force and project.status in [
            ProjectStatus.GRAPH_BUILDING,
            ProjectStatus.FAILED,
            ProjectStatus.GRAPH_COMPLETED,
        ]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None

        graph_name = data.get("graph_name", project.name or "MiroFish Graph")
        chunk_size = data.get("chunk_size", project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get(
            "chunk_overlap", project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP
        )
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap

        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({"success": False, "error": t("api.textNotFound")}), 400

        ontology = project.ontology
        if not ontology:
            return jsonify({"success": False, "error": t("api.ontologyNotFound")}), 400

        task_manager = TaskManager()
        task_id = task_manager.create_task(f"构建图谱: {graph_name}")

        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)

        current_locale = get_locale()

        def build_task():
            set_locale(current_locale)
            build_logger = get_logger("mirofish.build")
            try:
                task_manager.update_task(
                    task_id, status=TaskStatus.PROCESSING, message=t("progress.initGraphService")
                )
                builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
                task_manager.update_task(task_id, message=t("progress.textChunking"), progress=5)
                chunks = TextProcessor.split_text(
                    text, chunk_size=chunk_size, overlap=chunk_overlap
                )
                total_chunks = len(chunks)
                task_manager.update_task(
                    task_id, message=t("progress.creatingZepGraph"), progress=10
                )
                graph_id = builder.create_graph(name=graph_name)
                project.graph_id = graph_id
                ProjectManager.save_project(project)
                task_manager.update_task(
                    task_id, message=t("progress.settingOntology"), progress=15
                )
                builder.set_ontology(graph_id, ontology)

                def add_progress_callback(msg, progress_ratio):
                    task_manager.update_task(
                        task_id, message=msg, progress=15 + int(progress_ratio * 40)
                    )

                task_manager.update_task(
                    task_id, message=t("progress.addingChunks", count=total_chunks), progress=15
                )
                episode_uuids = builder.add_text_batches(
                    graph_id, chunks, batch_size=3, progress_callback=add_progress_callback
                )
                task_manager.update_task(
                    task_id, message=t("progress.waitingZepProcess"), progress=55
                )

                def wait_progress_callback(msg, progress_ratio):
                    task_manager.update_task(
                        task_id, message=msg, progress=55 + int(progress_ratio * 35)
                    )

                builder._wait_for_episodes(episode_uuids, wait_progress_callback)
                task_manager.update_task(
                    task_id, message=t("progress.fetchingGraphData"), progress=95
                )
                graph_data = builder.get_graph_data(graph_id)
                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)

                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    message=t("progress.graphBuildComplete"),
                    progress=100,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "node_count": graph_data.get("node_count", 0),
                        "edge_count": graph_data.get("edge_count", 0),
                        "chunk_count": total_chunks,
                    },
                )
            except Exception as e:
                build_logger.error(f"[{task_id}] 图谱构建失败: {str(e)}")
                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=t("progress.buildFailed", error=str(e)),
                    error=traceback.format_exc(),
                )

        threading.Thread(target=build_task, daemon=True).start()

        return jsonify(
            {
                "success": True,
                "data": {
                    "project_id": project_id,
                    "task_id": task_id,
                    "message": t("api.graphBuildStarted", taskId=task_id),
                },
            }
        )
    except Exception as e:
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


# ============== 任务查询接口 ==============


@graph_bp.route("/task/<task_id>", methods=["GET"])
def get_task(task_id: str):
    task = TaskManager().get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": t("api.taskNotFound", id=task_id)}), 404
    return jsonify({"success": True, "data": task.to_dict()})


@graph_bp.route("/tasks", methods=["GET"])
def list_tasks():
    tasks = TaskManager().list_tasks()
    return jsonify({"success": True, "data": [t.to_dict() for t in tasks], "count": len(tasks)})


# ============== 图谱数据接口 ==============


@graph_bp.route("/data/<graph_id>", methods=["GET"])
def get_graph_data(graph_id: str):
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({"success": False, "error": t("api.zepApiKeyMissing")}), 500
        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        graph_data = builder.get_graph_data(graph_id)
        return jsonify({"success": True, "data": graph_data})
    except Exception as e:
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@graph_bp.route("/delete/<graph_id>", methods=["DELETE"])
def delete_graph(graph_id: str):
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({"success": False, "error": t("api.zepApiKeyMissing")}), 500
        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        builder.delete_graph(graph_id)
        return jsonify({"success": True, "message": t("api.graphDeleted", id=graph_id)})
    except Exception as e:
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500
