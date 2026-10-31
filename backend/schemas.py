"""
Contrato da API entre o front-end (React) e o backend (FastAPI).

Cada classe é o formato JSON de uma requisição (...In) ou de uma resposta (...Out).
As rotas que usam estes formatos ficam em api.py; a documentação completa está em ../API.md.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Perfil do paciente (da tela de identificação; nome, CPF e data de nascimento não vão para o backend)
# --------------------------------------------------------------------------- #

class Perfil(BaseModel):
    idade: int | None = Field(default=None, ge=0, le=130)
    sexo: Literal["F", "M"] | None = None
    deficiencias: list[Literal["fisica", "visual", "auditiva", "intelectual"]] = []


# --------------------------------------------------------------------------- #
# GET /api/config
# --------------------------------------------------------------------------- #

class ConfigOut(BaseModel):
    tempo_pressao_s: int            # segundos do cronômetro da medição de pressão
    tempo_spo2_s: int               # segundos esperando a saturação do relógio
    spo2: float                     # SpO2 padrão (quando não há leitura do relógio)
    temp: float                     # temperatura padrão (ainda não há sensor)
    omron_simulado: bool            # True = medição de pressão falsa, sem o aparelho
    spo2_simulado: bool             # True = saturação falsa, sem o relógio
    usar_medidor: bool              # False = não há medidor: a pessoa digita a pressão
    usar_relogio: bool              # False = não há relógio: a saturação é digitada
    medidor: str | None             # nome do medidor de pressão ativo
    usar_camera: bool               # True = a câmera confere se é a mesma pessoa durante a triagem
    camera_simulada: bool           # True = modo de teste da câmera
    tempo_abandono_s: int           # titular fora da câmera por N s cancela a triagem (0 = nunca)
    modo_padrao: str                # "realtime" ou "classico"
    silencio_ms: int                # silêncio que encerra a fala do usuário
    nomes_sintomas: dict[str, str]  # chave do sintoma -> nome para mostrar na tela
    token_configurado: bool         # False = falta o token da OpenAI no .env


# --------------------------------------------------------------------------- #
# Modo clássico: transcrever, conversar e falar
# --------------------------------------------------------------------------- #

class TranscreverOut(BaseModel):
    texto: str  # vazio quando o áudio é curto demais


class Mensagem(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatIn(BaseModel):
    historico: list[Mensagem]
    perfil: Perfil | None = None  # adapta as perguntas (ex.: não pergunta de gravidez no sexo masculino)


class ChatOut(BaseModel):
    texto: str                 # o que a assistente vai falar
    sintomas_concluidos: bool  # True = entrevista terminou, ir para a pressão
    sintomas: list[str]        # chaves do catálogo (vazio enquanto não terminou)
    resumo: str                # uma frase com o que o usuário relatou


class FalarIn(BaseModel):
    texto: str


class FalarOut(BaseModel):
    id: str  # usado em GET /api/falar/{id} para tocar o áudio


# --------------------------------------------------------------------------- #
# Modo tempo real
# --------------------------------------------------------------------------- #

class RealtimeIn(BaseModel):
    perfil: Perfil | None = None


class RealtimeOut(BaseModel):
    chave: str             # chave temporária da OpenAI (o token de verdade não sai do backend)
    modelo: str            # modelo de voz usado na sessão
    texto_transicao: str   # fala que pede para medir a pressão
    prompt_resultado: str  # instruções para a sessão explicar o resultado da árvore


# --------------------------------------------------------------------------- #
# POST /api/pressao
# --------------------------------------------------------------------------- #

class PressaoOut(BaseModel):
    pas: float                 # pressão sistólica (mmHg)
    pad: float                 # pressão diastólica (mmHg)
    fc: float                  # frequência cardíaca (bpm)
    datahora: str              # data e hora da medição (ISO 8601)
    movimento_detectado: bool  # o aparelho detectou movimento durante a medição
    batimento_irregular: bool  # o aparelho detectou batimento irregular
    simulado: bool = False     # True no modo de teste do medidor


# --------------------------------------------------------------------------- #
# POST /api/classificar
# --------------------------------------------------------------------------- #

class PacienteIn(BaseModel):
    """Identificação do paciente (vai só para o banco de dados, não para a LLM).
    Sem validação rígida aqui: um CPF estranho não pode impedir a classificação; banco.py confere."""
    nome: str = Field(default="", max_length=100)
    cpf: str = Field(default="", max_length=14)
    data_nascimento: str | None = None  # dd/mm/aaaa


class RegistroTriagem(BaseModel):
    """O que o banco precisa além do que a árvore já recebe."""
    paciente: PacienteIn
    modo_questionario: Literal["ESCRITO", "VOZ"] | None = None
    resumo: str | None = None
    conversa: list[Mensagem] = []
    pressao_origem: Literal["SENSOR", "MANUAL"] = "MANUAL"
    pressao_experimental: bool = False   # True = medição simulada (modo de teste)
    spo2_origem: Literal["SENSOR", "MANUAL"] = "MANUAL"
    spo2_experimental: bool = False


class ClassificarIn(BaseModel):
    sintomas: list[str]        # chaves do catálogo da árvore
    pas: float
    pad: float
    fc: float
    spo2: float | None = None  # sem valor = SPO2_MANUAL do .env
    temp: float | None = None  # sem valor = TEMP_MANUAL do .env
    explicar: bool = True      # False no modo tempo real (quem explica é a sessão de voz)
    perfil: Perfil | None = None
    registro: RegistroTriagem | None = None  # dados para gravar no banco (sem = não grava)


class ClassificarOut(BaseModel):
    resultado: dict[str, Any]  # saída completa de arvore_decisao.classificar_risco
    texto: str | None          # explicação falada (None quando explicar = False)
    triagem_id: int | None = None  # id da triagem no banco (None = não gravou)


# --------------------------------------------------------------------------- #
# Saturação (SpO2) do Galaxy Watch
# --------------------------------------------------------------------------- #

class Spo2RelogioIn(BaseModel):
    """O que o app do relógio envia para POST /spo2 (mesmo formato do projeto-spo2)."""
    spo2: int = Field(ge=0, le=100)
    timestamp: int = Field(gt=0)  # horário da medição no relógio (ms desde 1970)


class Spo2Leitura(BaseModel):
    spo2: int
    timestamp: int        # horário da medição no relógio (ms)
    recebido_em_ms: int   # quando o backend recebeu (ms)
    simulado: bool


class Spo2InicioOut(BaseModel):
    inicio_ms: int  # leituras recebidas a partir deste horário valem para esta triagem
    simulado: bool


class Spo2UltimaOut(BaseModel):
    leitura: Spo2Leitura | None


# --------------------------------------------------------------------------- #
# Tela de configuração (/api/ajustes)
# --------------------------------------------------------------------------- #

class Medidor(BaseModel):
    id: str
    nome: str
    modelo: str
    endereco: str | None   # endereço Bluetooth; None = qualquer Omron por perto
    pareado: bool


class AjustesOut(BaseModel):
    modo_teste_pressao: bool
    modo_teste_spo2: bool
    usar_medidor: bool
    usar_relogio: bool
    tempo_pressao_s: int
    tempo_spo2_s: int
    spo2: float
    temp: float
    medidores: list[Medidor]
    medidor_ativo: str | None
    salvar_no_banco: bool     # grava cada triagem no MySQL do XAMPP
    usar_camera: bool
    modo_teste_camera: bool
    camera_indice: int
    limiar_camera: float
    tempo_troca_s: float
    tempo_abandono_s: int
    modelos: dict[str, str]   # modelos que dá para cadastrar (chave -> nome)
    url_relogio: str          # endereço para colocar no SERVER_URL do app do relógio


class AjustesIn(BaseModel):
    """Só os campos enviados são alterados."""
    modo_teste_pressao: bool | None = None
    modo_teste_spo2: bool | None = None
    usar_medidor: bool | None = None
    usar_relogio: bool | None = None
    tempo_pressao_s: int | None = Field(default=None, ge=20, le=600)
    tempo_spo2_s: int | None = Field(default=None, ge=20, le=600)
    spo2: float | None = Field(default=None, ge=50, le=100)
    temp: float | None = Field(default=None, ge=30, le=45)
    medidor_ativo: str | None = None
    salvar_no_banco: bool | None = None
    usar_camera: bool | None = None
    modo_teste_camera: bool | None = None
    camera_indice: int | None = Field(default=None, ge=0, le=9)
    limiar_camera: float | None = Field(default=None, ge=0.3, le=0.8)
    tempo_troca_s: float | None = Field(default=None, ge=1, le=30)
    tempo_abandono_s: int | None = Field(default=None, ge=0, le=900)


class MedidorIn(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    modelo: str = "omron_hem7156t"
    endereco: str | None = Field(default=None, pattern=r"^$|^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class MedidorEncontrado(BaseModel):
    nome: str
    endereco: str
    rssi: int | None = None


# --------------------------------------------------------------------------- #
# Banco de dados
# --------------------------------------------------------------------------- #

class EncaminhamentoIn(BaseModel):
    paciente: PacienteIn
    perfil: Perfil | None = None
    motivos: list[str] = []


class EncaminhamentoOut(BaseModel):
    triagem_id: int | None  # None = não gravou (banco desligado ou fora do ar)


class BancoEstadoOut(BaseModel):
    banco: str
    servidor: str
    conectado: bool
    erro: str | None
    total_triagens: int | None
    salvar_no_banco: bool


class TriagemResumo(BaseModel):
    id: int
    data_hora_inicio: str
    status: str
    modo_questionario: str | None
    paciente: str
    cor: str | None
    nivel: str | None
    motivo: str | None


# --------------------------------------------------------------------------- #
# Login da tela de configuração
# --------------------------------------------------------------------------- #

class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=150)
    senha: str = Field(min_length=1, max_length=200)


class LoginOut(BaseModel):
    token: str  # vai no cabeçalho "Authorization: Bearer <token>" das rotas da configuração
    nome: str
    email: str


# --------------------------------------------------------------------------- #
# Usuários (seção "Usuários" da tela de configuração)
# --------------------------------------------------------------------------- #

class UsuarioOut(BaseModel):
    id: int
    nome: str
    email: str
    perfil: Literal["ADMIN", "GESTOR", "ATENDENTE"]
    ativo: bool                # False = bloqueado (pelo admin ou por 5 senhas erradas)
    tentativas_invalidas: int
    criado_em: str


class UsuarioIn(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=150)
    senha: str = Field(min_length=8, max_length=200)
    perfil: Literal["ADMIN", "GESTOR", "ATENDENTE"] = "ATENDENTE"


class UsuarioAtivoIn(BaseModel):
    ativo: bool  # False = bloquear, True = desbloquear


# --------------------------------------------------------------------------- #
# Câmera: mesma pessoa do começo ao fim da triagem (presenca.py)
# --------------------------------------------------------------------------- #

class PresencaOut(BaseModel):
    sessao: str | None
    estado: Literal["aguardando_rosto", "presente", "ausente", "cancelada", "erro", "desligado"]
    mensagem: str      # texto para a tela (ex.: "Volte para a frente do totem...")
    simulado: bool     # True = modo de teste, sem câmera
    ausente_s: int     # há quantos segundos o titular saiu da frente da câmera


class SimularPresencaIn(BaseModel):
    evento: Literal["sair", "voltar", "trocar"]


class CameraTesteOut(BaseModel):
    ok: bool
    mensagem: str
    rostos: int | None  # rostos que a câmera vê agora


class CancelamentoIn(BaseModel):
    paciente: PacienteIn
    perfil: Perfil | None = None
    motivo: str = Field(max_length=500)
