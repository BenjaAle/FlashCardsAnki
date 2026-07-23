from pydantic import BaseModel


class Mensaje(BaseModel):
    texto: str
    chat_id: int


class NuevoChat(BaseModel):
    titulo: str


class ExtraerRequest(BaseModel):
    chat_id: int


class RenombrarRequest(BaseModel):
    titulo: str


class InyectarRequest(BaseModel):
    chat_id: int
    cartas: list


class NuevaHistoria(BaseModel):
    tematica: str
    nivel: str = "Avanzado C1"


class CartaUnicaRequest(BaseModel):
    palabra: str
    contexto: str


class EntrenamientoPares(BaseModel):
    fonema_1: str
    fonema_2: str