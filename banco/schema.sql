-- =============================================================================
-- Banco de dados da Triagem Inteligente (TCC 2026) — MySQL/MariaDB do XAMPP
--
-- Feito a partir do diagrama de classes. O backend cria tudo sozinho ao iniciar
-- (backend/banco.py), mas este arquivo também pode ser importado no phpMyAdmin
-- (http://localhost/phpmyadmin > Importar).
--
-- Mapeamento das classes:
--   Usuario / Atendente / Gestor  -> usuario (herança numa tabela só, coluna perfil;
--                                    ADMIN = acessa a tela de configuração)
--   Paciente                      -> paciente
--   Triagem                       -> triagem
--   FatorRisco (7)                -> fator_risco      + triagem_fator_risco (N:N)
--   Sintoma (catálogo, 91)        -> sintoma
--   SintomaRelatado               -> sintoma_relatado (Triagem 1 -> 0..* , Sintoma 1)
--   LeituraSinaisVitais           -> leitura_sinais_vitais (Triagem 1 -> 1..*)
--   Dispositivo                   -> dispositivo      (Leitura 0..* -> 0..1)
--   ClassificacaoRisco            -> classificacao_risco (Triagem 1 -> 0..1)
--   RegraCombinacao (27)          -> regra_combinacao (regras da ArvoreDecisao)
--   CorRisco (enumeração)         -> ENUM nas colunas de cor
--   AssistenteVoz, ArvoreDecisao  -> serviços (código), sem tabela
-- Os catálogos (sintoma, fator_risco, regra_combinacao) são preenchidos a partir de
-- arvore_decisao/arvore_decisao.py, para nunca ficarem diferentes da árvore.
-- =============================================================================

CREATE DATABASE IF NOT EXISTS triagem_inteligente
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE triagem_inteligente;

-- Usuario (Atendente e Gestor herdam de Usuario)
CREATE TABLE IF NOT EXISTS usuario (
  id                    INT AUTO_INCREMENT PRIMARY KEY,
  nome                  VARCHAR(100) NOT NULL,
  email                 VARCHAR(150) NOT NULL UNIQUE,
  senha_hash            VARCHAR(255) NOT NULL,
  perfil                ENUM('ATENDENTE', 'GESTOR', 'ADMIN') NOT NULL DEFAULT 'ATENDENTE',
  ativo                 BOOLEAN NOT NULL DEFAULT TRUE,
  tentativas_invalidas  INT NOT NULL DEFAULT 0,
  criado_em             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- bancos criados antes do perfil ADMIN existir
ALTER TABLE usuario MODIFY perfil ENUM('ATENDENTE', 'GESTOR', 'ADMIN') NOT NULL DEFAULT 'ATENDENTE';

CREATE TABLE IF NOT EXISTS paciente (
  id               INT AUTO_INCREMENT PRIMARY KEY,
  nome             VARCHAR(100) NOT NULL,
  cpf              CHAR(11) NOT NULL UNIQUE,        -- só os números
  rg               VARCHAR(20) NULL,
  data_nascimento  DATE NULL,
  idade            INT NULL,                         -- idade no último atendimento
  sexo             ENUM('F', 'M') NULL,
  email            VARCHAR(150) NULL,
  criado_em        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS triagem (
  id                  INT AUTO_INCREMENT PRIMARY KEY,
  paciente_id         INT NOT NULL,                  -- Paciente 1 "possui" 0..* Triagem
  atendente_id        INT NULL,                      -- Atendente 1 "conduz" 0..* Triagem (NULL = totem sozinho)
  data_hora_inicio    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  modo_questionario   ENUM('ESCRITO', 'VOZ') NULL,
  resumo_relato       TEXT NULL,
  status              ENUM('EM_ANDAMENTO', 'CONCLUIDA', 'ENCAMINHADA', 'CANCELADA') NOT NULL DEFAULT 'EM_ANDAMENTO',
  deficiencias        VARCHAR(100) NULL,             -- ex.: "fisica,visual" (da identificação)
  motivo_encaminhamento TEXT NULL,                   -- quando foi encaminhada direto à enfermagem
  motivo_cancelamento TEXT NULL,                     -- quando a câmera cancelou (outra pessoa assumiu)
  conversa            LONGTEXT NULL,                 -- histórico da conversa com a assistente (JSON)
  CONSTRAINT fk_triagem_paciente  FOREIGN KEY (paciente_id)  REFERENCES paciente(id),
  CONSTRAINT fk_triagem_atendente FOREIGN KEY (atendente_id) REFERENCES usuario(id) ON DELETE SET NULL,
  INDEX idx_triagem_data (data_hora_inicio),
  INDEX idx_triagem_status (status)
) ENGINE=InnoDB;

-- bancos criados antes do cancelamento pela câmera existir
ALTER TABLE triagem ADD COLUMN IF NOT EXISTS motivo_cancelamento TEXT NULL AFTER motivo_encaminhamento;

CREATE TABLE IF NOT EXISTS fator_risco (
  chave      VARCHAR(50) PRIMARY KEY,
  descricao  VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS triagem_fator_risco (
  triagem_id        INT NOT NULL,
  fator_risco_chave VARCHAR(50) NOT NULL,
  PRIMARY KEY (triagem_id, fator_risco_chave),
  CONSTRAINT fk_tfr_triagem FOREIGN KEY (triagem_id) REFERENCES triagem(id) ON DELETE CASCADE,
  CONSTRAINT fk_tfr_fator   FOREIGN KEY (fator_risco_chave) REFERENCES fator_risco(chave)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sintoma (
  chave      VARCHAR(50) PRIMARY KEY,
  rotulo     VARCHAR(100) NOT NULL,
  descricao  VARCHAR(255) NOT NULL,
  grupo      VARCHAR(60) NOT NULL,                   -- sistema do corpo (Neurológico, Respiratório, ...)
  cor_base   ENUM('VERMELHO', 'LARANJA', 'AMARELO', 'VERDE', 'AZUL') NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sintoma_relatado (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  triagem_id     INT NOT NULL,
  sintoma_chave  VARCHAR(50) NOT NULL,
  intensidade    ENUM('LEVE', 'MODERADA', 'INTENSA') NULL,
  origem         ENUM('ESCRITO', 'VOZ') NULL,
  CONSTRAINT fk_sr_triagem FOREIGN KEY (triagem_id) REFERENCES triagem(id) ON DELETE CASCADE,
  CONSTRAINT fk_sr_sintoma FOREIGN KEY (sintoma_chave) REFERENCES sintoma(chave),
  UNIQUE KEY uq_sr (triagem_id, sintoma_chave)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS dispositivo (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  identificador  VARCHAR(60) NOT NULL UNIQUE,        -- id do medidor na tela de configuração, ou "relogio"
  nome           VARCHAR(100) NOT NULL,
  tipo           ENUM('MONITOR_PA', 'RELOGIO') NOT NULL,
  modelo         VARCHAR(100) NOT NULL,
  protocolo      ENUM('BLE', 'WIFI_HTTP') NOT NULL,
  endereco       VARCHAR(30) NULL                    -- endereço Bluetooth, quando houver
) ENGINE=InnoDB;

-- Uma triagem tem 1..* leituras: uma do medidor de pressão (pas, pad, fc) e uma da
-- saturação/temperatura (spo2 do relógio, temperatura digitada). Campos que a leitura não mede ficam NULL.
CREATE TABLE IF NOT EXISTS leitura_sinais_vitais (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  triagem_id      INT NOT NULL,
  dispositivo_id  INT NULL,
  pas             INT NULL,
  pad             INT NULL,
  fc              INT NULL,
  spo2            INT NULL,
  temperatura     DECIMAL(4,1) NULL,
  origem          ENUM('SENSOR', 'MANUAL') NOT NULL,
  experimental    BOOLEAN NOT NULL DEFAULT FALSE,    -- TRUE = modo de teste (valor simulado)
  data_hora       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_lsv_triagem     FOREIGN KEY (triagem_id) REFERENCES triagem(id) ON DELETE CASCADE,
  CONSTRAINT fk_lsv_dispositivo FOREIGN KEY (dispositivo_id) REFERENCES dispositivo(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS classificacao_risco (
  id                       INT AUTO_INCREMENT PRIMARY KEY,
  triagem_id               INT NOT NULL UNIQUE,      -- Triagem 1 -> 0..1 ClassificacaoRisco
  cor                      ENUM('VERMELHO', 'LARANJA', 'AMARELO', 'VERDE', 'AZUL') NOT NULL,
  nivel                    ENUM('N1', 'N2', 'N3', 'N4', 'N5', 'N6') NOT NULL,
  tempo_alvo_min           INT NOT NULL,
  motivo                   VARCHAR(500) NOT NULL,
  achados_secundarios      LONGTEXT NULL,            -- JSON: lista de outras regras que dispararam
  news2                    INT NULL,
  atendimento_prioritario  BOOLEAN NOT NULL DEFAULT FALSE,
  data_hora                DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_cr_triagem FOREIGN KEY (triagem_id) REFERENCES triagem(id) ON DELETE CASCADE,
  INDEX idx_cr_cor (cor)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS regra_combinacao (
  id        VARCHAR(20) PRIMARY KEY,                 -- ex.: LARANJA_03
  condicao  TEXT NOT NULL,                           -- condição como está no código da árvore
  cor       ENUM('VERMELHO', 'LARANJA', 'AMARELO', 'VERDE', 'AZUL') NOT NULL,
  motivo    VARCHAR(255) NOT NULL
) ENGINE=InnoDB;
