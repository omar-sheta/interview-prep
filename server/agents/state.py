"""
Agent State Schema for BeePrepared.
Defines the state that flows through the LangGraph agent.
"""

from typing import Any, Literal, TypedDict


# Interview status enum values
InterviewStatus = Literal["warmup", "technical", "feedback"]


class InterviewState(TypedDict):
    """
    State schema for the BeePrepared LangGraph.
    
    This state is passed between nodes in the graph and maintains
    the interview context throughout the conversation.
    """
    
    # Chat history - list of messages (HumanMessage, AIMessage, etc.)
    messages: list[Any]
    
    # The current interview question being asked
    current_question: str
    
    # Transcribed audio chunks from the candidate
    transcript_chunks: list[str]
    
    # Current phase of the interview
    status: InterviewStatus
    
    # Accumulated feedback from the evaluation nodes
    feedback_logs: list[dict]
