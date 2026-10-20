"""Inicia e encerra somente o agendador da operação simulada."""
def post_worker_init(worker):
    from operacao import iniciar_agendador
    worker.operacao_controles = iniciar_agendador(worker.wsgi)


def worker_exit(server, worker):
    controles = getattr(worker, 'operacao_controles', None)
    if controles:
        controles[0].set()
        controles[1].set()
