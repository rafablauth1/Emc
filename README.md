<div align="center">

# Automatizador de Ensaios EMC

**Planejamento, execução e registro de ensaios de imunidade da série IEC 61000-4**

![Status](https://img.shields.io/badge/status-incorporado%20ao%20HALO-8A6D3B?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-Qt%206-41CD52?style=flat-square&logo=qt&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?style=flat-square&logo=windows&logoColor=white)

</div>

> **Este projeto foi incorporado ao [HALO](https://github.com/rafablauth1/Halo)** em 28/08/2026, como a seção
> **EMC · Imunidade**. O desenvolvimento continua lá; este repositório fica como referência histórica.

---

## Visão geral

Aplicação desktop para o laboratório de EMC que organiza os ensaios de imunidade de um EUT do planejamento ao
laudo, com controle remoto dos geradores por GPIB.

| Aba | Descrição |
|---|---|
| **Planner** | Projetos e EUTs, ensaios por norma e porta (alimentação e/ou comunicação) |
| **Execução** | Roda o ensaio contra o driver do gerador, com progresso gravado a cada etapa |
| **Registro de Energia** | Leituras do medidor de energia antes e depois de cada evento de imunidade |
| **Relatórios** | Laudo em `.docx` a partir de modelos |
| **Configurações** | Modo simulado, endereços GPIB e parâmetros dos instrumentos |
| **Comandos** | Editor dos comandos de cada equipamento |

### Normas

IEC 61000-4-2, 4-3, 4-4, 4-5, 4-6, 4-11 e 4-19. Os ensaios **4-4**, **4-5** e **4-11** são automatizados; os
demais seguem roteiros manuais.

### Instrumentos

| Equipamento | Uso |
|---|---|
| EM Test UCS 500N | Burst (4-4) e surto (4-5) |
| Chroma 615xx | Quedas e interrupções de tensão (4-11) |
| Agilent 53131A | Contador de pulsos do medidor sob ensaio |

## Instalação

Requer **Python 3.11+** no Windows e, para hardware real, **NI-VISA** com adaptador GPIB.

```bat
git clone https://github.com/rafablauth1/Emc.git
cd Emc
setup_lab.bat       :: cria o ambiente virtual e instala as dependências
iniciar_app.bat     :: abre o aplicativo
```

Para usar com os instrumentos: confirme no NI-MAX que eles aparecem (`GPIB0::N::INSTR`), desmarque
**Modo simulado** em Configurações e ajuste os endereços GPIB.

## Estrutura do projeto

```
app/
  main.py           ponto de entrada
  config.py         caminhos, normas e parâmetros
  core/             planner, sessões de ensaio, registro de energia, relatórios, banco SQLite
  gui/              telas PySide6
  instruments/      drivers SCPI/GPIB (UCS 500N, Chroma 615xx, Agilent 53131A)
setup_lab.bat       instalação no PC do laboratório
iniciar_app.bat     atalho de execução
```

## Stack

PySide6 · PyVISA · python-docx · SQLite
