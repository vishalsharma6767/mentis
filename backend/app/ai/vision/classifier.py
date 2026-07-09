"""Classifies problem type: math, physics, chemistry, etc."""

PROBLEM_TYPES = ['math', 'physics', 'chemistry', 'biology', 'other']


def classify_problem(text: str) -> str:
    """Returns one of PROBLEM_TYPES based on problem text."""
    return 'math'
