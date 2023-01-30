def get_slo_namesape_and_sli_name(namespace, slo_type, slo, test=False):
    slo_namespace = 'SLO/' + namespace.replace('AWS/','')
    if test:
        slo_namespace = 'Test/' + slo_namespace
    sli_name = slo_type
    if slo_type == 'Latency':
        sli_name += 'P' + str(slo[0])
    return slo_namespace, sli_name