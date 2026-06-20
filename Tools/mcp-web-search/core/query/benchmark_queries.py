"""Complex multilingual query corpus for search quality comparisons."""

BENCHMARK_QUERIES = [
    {
        "id": "postgres-serializable-predicate-locks",
        "language": "en",
        "class": "technical",
        "query": (
            "PostgreSQL SSI predicate locks false positive serialization failures "
            "read-only deferrable transaction mitigation"
        ),
    },
    {
        "id": "ru-arbitration-subsidiary-liability",
        "language": "ru",
        "class": "legal",
        "query": (
            "субсидиарная ответственность контролирующего должника лица "
            "презумпция причинения вреда судебная практика арбитраж"
        ),
    },
    {
        "id": "ko-kubernetes-topology-spread",
        "language": "ko",
        "class": "technical",
        "query": (
            "Kubernetes topology spread constraints minDomains "
            "whenUnsatisfiable DoNotSchedule 동작 차이"
        ),
    },
    {
        "id": "fr-quic-loss-recovery",
        "language": "fr",
        "class": "technical",
        "query": (
            "QUIC récupération de pertes PTO persistent congestion "
            "différence avec TCP RTO RFC 9002"
        ),
    },
    {
        "id": "ja-solid-state-electrolyte",
        "language": "ja",
        "class": "academic",
        "query": (
            "硫化物系全固体電池 固体電解質 界面抵抗 "
            "リチウムデンドライト 抑制 メカニズム"
        ),
    },
    {
        "id": "es-cjeu-legitimate-interest",
        "language": "es",
        "class": "legal",
        "query": (
            "TJUE interés legítimo RGPD prueba de ponderación "
            "marketing directo jurisprudencia"
        ),
    },
]
