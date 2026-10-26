"""The shapes of what the model must return. Pydantic checks every one of them, so a model that answers in the wrong shape is caught, not trusted."""
from pydantic import BaseModel, Field


class Grade(BaseModel):
    """Is the evidence we retrieved enough to answer the question?"""
    sufficient: bool = Field(description="True only if the documents contain what is needed to answer")
    reason: str = Field(description="One short sentence saying why")


class Answer(BaseModel):
    """A grounded answer: the text, and the ids of the chunks it relied on."""
    text: str = Field(description="The answer, using only the documents")
    cited_chunk_ids: list[str] = Field(description="Ids of the chunks the answer relied on; never an id that was not provided")


class Rewrite(BaseModel):
    query: str = Field(description="A better search query for the same question")


NOTICE = "You are talking to an AI assistant. Its answers come from Dropline documents and can be wrong: check the sources it lists."
IDK = "I do not know. I could not find this in the documents I have."
MAX_ATTEMPTS = 2        # a retrieval that fails twice stops, instead of looping forever (the classic agent failure)
