"""O agendador acompanha cada worker; a reserva no banco limita as chamadas."""
def post_worker_init(worker):
    from importador_voos import iniciar
    worker.importador_parar = iniciar(worker.wsgi)


def worker_exit(server, worker):
    parar = getattr(worker, 'importador_parar', None)
    if parar:
        parar.set()
