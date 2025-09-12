
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from app.db import get_session
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.schemas.response import ApiResponse
from app.services import project_service
from typing import List

router = APIRouter()

@router.post("/", response_model=ApiResponse[ProjectRead])
def create_project_endpoint(project_in: ProjectCreate, session: Session = Depends(get_session)):
    project = project_service.create_project(session=session, project_in=project_in)
    return ApiResponse(data=project)

@router.get("/", response_model=ApiResponse[List[ProjectRead]])
def get_projects_endpoint(session: Session = Depends(get_session)):
    projects = project_service.get_projects(session=session)
    return ApiResponse(data=projects)

@router.get("/free", response_model=ApiResponse[ProjectRead])
def get_free_project_endpoint(session: Session = Depends(get_session)):
    proj = project_service.get_or_create_free_project(session=session)
    return ApiResponse(data=proj)

@router.get("/{project_id}", response_model=ApiResponse[ProjectRead])
def get_project_endpoint(project_id: int, session: Session = Depends(get_session)):
    project = project_service.get_project(session=session, project_id=project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ApiResponse(data=project)

@router.put("/{project_id}", response_model=ApiResponse[ProjectRead])
def update_project_endpoint(project_id: int, project_in: ProjectUpdate, session: Session = Depends(get_session)):
    project = project_service.update_project(session=session, project_id=project_id, project_in=project_in)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ApiResponse(data=project)

@router.delete("/{project_id}", response_model=ApiResponse)
def delete_project_endpoint(project_id: int, session: Session = Depends(get_session)):
    success = project_service.delete_project(session=session, project_id=project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    return ApiResponse(message="Project deleted successfully") 