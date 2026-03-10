"""Custom exception classes and error handlers."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from typing import Union


class IrrelevantQuestionError(Exception):
    """Raised when a question is not relevant to the dataset."""
    
    def __init__(self, message: str = "Question not relevant to dataset"):
        self.message = message
        super().__init__(self.message)


class DatasetNotFoundError(Exception):
    """Raised when a dataset is not found."""
    
    def __init__(self, dataset_id: str):
        self.dataset_id = dataset_id
        self.message = f"Dataset with ID {dataset_id} not found"
        super().__init__(self.message)


class FileProcessingError(Exception):
    """Raised when file processing fails."""
    
    def __init__(self, message: str = "Failed to process file"):
        self.message = message
        super().__init__(self.message)


class AgentExecutionError(Exception):
    """Raised when agent execution fails."""
    
    def __init__(self, message: str = "Agent execution failed"):
        self.message = message
        super().__init__(self.message)


async def irrelevant_question_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle irrelevant question errors."""
    assert isinstance(exc, IrrelevantQuestionError)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "irrelevant_question",
            "message": exc.message,
            "detail": "Please ask a question that relates to the columns and data in your uploaded dataset."
        }
    )


async def dataset_not_found_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle dataset not found errors."""
    assert isinstance(exc, DatasetNotFoundError)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": "dataset_not_found",
            "message": exc.message,
            "dataset_id": exc.dataset_id
        }
    )


async def file_processing_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle file processing errors."""
    assert isinstance(exc, FileProcessingError)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "file_processing_error",
            "message": exc.message
        }
    )


async def agent_execution_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle agent execution errors."""
    assert isinstance(exc, AgentExecutionError)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "agent_execution_error",
            "message": exc.message,
            "detail": "The AI agent encountered an error while processing your query."
        }
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers with the FastAPI app."""
    
    app.add_exception_handler(IrrelevantQuestionError, irrelevant_question_exception_handler)
    app.add_exception_handler(DatasetNotFoundError, dataset_not_found_exception_handler)
    app.add_exception_handler(FileProcessingError, file_processing_exception_handler)
    app.add_exception_handler(AgentExecutionError, agent_execution_exception_handler)
