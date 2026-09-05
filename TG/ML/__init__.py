"""
Módulo de regressão: projeta o IDEB de um município para o próximo ciclo.

Ordem do pipeline: dados -> dataset -> validacao -> prever.
Ver `ML/REGRESSAO.md` para as decisões de design.

Este arquivo era um shim de `sys.path`: os módulos daqui se importavam por nome
simples (`from dados import ...`) para poderem rodar com `cd ML && python
dados.py`, e o shim existia para que isso não quebrasse quando alguém importasse
via `ML.dados`. Com todos os módulos usando import absoluto a partir da raiz do
projeto, o shim deixou de ser necessário — rode com `python -m ML.dados`.
"""
