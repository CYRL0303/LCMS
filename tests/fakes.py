from collections.abc import Callable
from datetime import UTC, datetime

from legacy_pilot.code_knowledge_core.adapter import CodeKnowledgeCoreAdapter
from legacy_pilot.contracts.models import (
    Edge,
    EvidenceRef,
    GraphContext,
    GraphQuery,
    GraphSnapshot,
    IncidentMatch,
    IncidentQuery,
    IncidentRecord,
    Node,
    RepoIndexRequest,
)
from legacy_pilot.incident_memory_store.adapter import (
    IncidentMemoryStoreAdapter,
    _rank_similar_records,
)


class TestCodeKnowledgeCoreAdapter(CodeKnowledgeCoreAdapter):
    __test__ = False

    def __init__(self, now: Callable[[], datetime] | None = None):
        self._now = now or (lambda: datetime.now(UTC))

    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot:
        evidence = self._evidence_ref(
            evidence_id="EV-REPO-001",
            trace_id=f"TRACE-INDEX-{request.repo_id}",
            source_type="code",
            source_id=request.repo_uri,
            file_path="src/main/java/DatasetService.java",
            start_line=1,
            end_line=80,
            excerpt="class DatasetService { ... }",
            extraction_method="java_parser",
            confidence=0.95,
        )
        controller = Node(
            node_id="NODE-DATASET-CONTROLLER",
            graph_id="GRAPH-DEMO",
            repo_id=request.repo_id,
            type="Class",
            name="DatasetController",
            qualified_name="com.legacy.DatasetController",
            evidence_refs=[evidence],
        )
        service = Node(
            node_id="NODE-DATASET-SERVICE",
            graph_id="GRAPH-DEMO",
            repo_id=request.repo_id,
            type="Class",
            name="DatasetService",
            qualified_name="com.legacy.DatasetService",
            evidence_refs=[evidence],
        )
        edge = Edge(
            edge_id="EDGE-CONTROLLER-SERVICE",
            graph_id="GRAPH-DEMO",
            source_node_id=controller.node_id,
            target_node_id=service.node_id,
            type="CALLS",
            confidence=0.92,
            extraction_method="java_parser",
            evidence_refs=[evidence],
        )
        return GraphSnapshot(
            graph_id="GRAPH-DEMO",
            repo_id=request.repo_id,
            nodes=[controller, service],
            edges=[edge],
            evidence_refs=[evidence],
            generated_at=self._now(),
        )

    def query_graph(self, query: GraphQuery) -> GraphContext:
        evidence = self._evidence_ref(
            evidence_id="EV-GRAPH-001",
            trace_id=query.trace_id,
            source_type="code",
            source_id="DatasetService.java",
            file_path="src/main/java/DatasetService.java",
            start_line=40,
            end_line=45,
            excerpt="return datasetMapper.selectVersionById(req.getDatasetId());",
            extraction_method="java_parser",
            confidence=0.95,
        )
        log_evidence = self._evidence_ref(
            evidence_id="EV-LOG-001",
            trace_id=query.trace_id,
            source_type="log",
            source_id=query.trace_id,
            excerpt="NullPointerException at DatasetService.getVersion(DatasetService.java:42)",
            extraction_method="regex",
            confidence=0.88,
        )
        controller = Node(
            node_id="NODE-DATASET-CONTROLLER-GET-VERSION",
            graph_id=query.graph_id,
            repo_id=query.repo_id,
            type="API Endpoint",
            name="/api/dataset/version",
            qualified_name="DatasetController.getVersion",
            evidence_refs=[evidence],
        )
        service = Node(
            node_id="NODE-DATASET-SERVICE-GET-VERSION",
            graph_id=query.graph_id,
            repo_id=query.repo_id,
            type="Method",
            name="getVersion",
            qualified_name="DatasetService.getVersion",
            evidence_refs=[evidence],
        )
        mapper = Node(
            node_id="NODE-DATASET-MAPPER-SELECT-VERSION",
            graph_id=query.graph_id,
            repo_id=query.repo_id,
            type="Mapper",
            name="selectVersionById",
            qualified_name="DatasetMapper.selectVersionById",
            evidence_refs=[evidence],
        )
        controller_to_service = Edge(
            edge_id="EDGE-CONTROLLER-SERVICE-GET-VERSION",
            graph_id=query.graph_id,
            source_node_id=controller.node_id,
            target_node_id=service.node_id,
            type="CALLS",
            confidence=0.9,
            extraction_method="java_parser",
            evidence_refs=[evidence],
        )
        service_to_mapper = Edge(
            edge_id="EDGE-SERVICE-MAPPER-SELECT-VERSION",
            graph_id=query.graph_id,
            source_node_id=service.node_id,
            target_node_id=mapper.node_id,
            type="USES_MAPPER",
            confidence=0.86,
            extraction_method="java_parser",
            evidence_refs=[evidence],
        )
        return GraphContext(
            trace_id=query.trace_id,
            matched_nodes=[controller, service, mapper],
            matched_edges=[controller_to_service, service_to_mapper],
            graph_paths=[
                [
                    "DatasetController.getVersion",
                    "DatasetService.getVersion",
                    "DatasetMapper.selectVersionById",
                    "dataset_version",
                ]
            ],
            evidence_refs=[evidence, log_evidence],
            confidence=0.88,
        )

    def _evidence_ref(
        self,
        *,
        evidence_id: str,
        trace_id: str,
        source_type: str,
        source_id: str,
        extraction_method: str,
        confidence: float,
        file_path: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        excerpt: str | None = None,
    ) -> EvidenceRef:
        return EvidenceRef(
            evidence_id=evidence_id,
            trace_id=trace_id,
            source_type=source_type,
            source_id=source_id,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            excerpt=excerpt,
            excerpt_hash=f"test-{evidence_id.lower()}",
            extraction_method=extraction_method,
            confidence=confidence,
            created_at=self._now(),
        )


class TestInMemoryIncidentMemoryStoreAdapter(IncidentMemoryStoreAdapter):
    __test__ = False

    def __init__(self):
        self._records: dict[str, IncidentRecord] = {}

    def save_incident(self, record: IncidentRecord) -> IncidentRecord:
        self._records[record.incident_id] = record
        return record

    def load_incident(self, incident_id: str) -> IncidentRecord | None:
        return self._records.get(incident_id)

    def find_similar_incidents(
        self,
        query: IncidentQuery,
        *,
        limit: int = 5,
    ) -> list[IncidentMatch]:
        return _rank_similar_records(
            query=query,
            records=list(self._records.values()),
            limit=limit,
        )
