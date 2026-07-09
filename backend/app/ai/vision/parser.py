"""Parses extracted text into structured problem data (equations, variables, question)."""

from pydantic import BaseModel


class ParsedProblem(BaseModel):
    question: str
    equations: list[str] = []
    variables: dict[str, str] = {}
    problem_type: str = 'math'
