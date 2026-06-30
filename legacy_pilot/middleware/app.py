from fastapi import FastAPI, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from legacy_pilot.contracts.enums import ErrorCode
from legacy_pilot.contracts.errors import ContractError, ContractViolation
from legacy_pilot.contracts.models import (
    AlertEvent,
    DeleteGraphResponse,
    EvidenceBundle,
    GraphContext,
    GraphQuery,
    GraphSnapshot,
    IncidentMatch,
    IncidentQuery,
    IncidentRecord,
    RCAReport,
    RepoIndexRequest,
    ReviewedRCAReport,
    SaveIncidentRequest,
    StoredGraph,
)
from legacy_pilot.contracts.runtime_credentials import (
    RuntimeCredentials,
    clean_secret,
    use_runtime_credentials,
)
from legacy_pilot.contracts.validators import SUPPORTED_CONTRACT_VERSION
from legacy_pilot.middleware.router import MiddlewareRouter


def _runtime_credentials_from_headers(
    *,
    qwen_api_key: str | None = None,
    github_token: str | None = None,
    gitlab_token: str | None = None,
) -> RuntimeCredentials:
    return RuntimeCredentials(
        qwen_api_key=clean_secret(qwen_api_key),
        github_token=clean_secret(github_token),
        gitlab_token=clean_secret(gitlab_token),
    )


def create_app(router: MiddlewareRouter | None = None) -> FastAPI:
    middleware_router = router or MiddlewareRouter()
    app = FastAPI(
        title="LegacyPilot Interface Contract Middleware",
        version="0.1.0",
    )

    @app.exception_handler(ContractViolation)
    async def contract_violation_handler(_, exc: ContractViolation) -> JSONResponse:
        status_code = 400
        if exc.error.error_code in {
            ErrorCode.USER_CONFIRMATION_REQUIRED,
            ErrorCode.RESOURCE_IN_USE,
        }:
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content=exc.error.model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_, exc: RequestValidationError) -> JSONResponse:
        missing_fields = [
            str(error["loc"][-1])
            for error in exc.errors()
            if error.get("type") == "missing" and error.get("loc")
        ]
        error_code = ErrorCode.TRACE_REQUIRED if "trace_id" in missing_fields else ErrorCode.VALIDATION_ERROR
        message = (
            "trace_id is required for runtime contract objects."
            if error_code == ErrorCode.TRACE_REQUIRED
            else "Request body failed contract validation."
        )
        error = ContractError(
            trace_id=None,
            error_code=error_code,
            message=message,
            source_module="interface_contract_middleware",
            recoverable=True,
            missing_fields=missing_fields,
        )
        return JSONResponse(
            status_code=422,
            content=error.model_dump(mode="json"),
        )

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "service": "legacy-pilot-interface-contract-middleware",
            "contract_version": SUPPORTED_CONTRACT_VERSION,
            "backends": middleware_router.runtime_config(),
        }

    @app.post("/v1/repos/index", response_model=GraphSnapshot)
    async def index_repo(
        request: RepoIndexRequest,
        qwen_api_key: str | None = Header(default=None, alias="X-LegacyPilot-Qwen-Api-Key"),
        github_token: str | None = Header(default=None, alias="X-LegacyPilot-GitHub-Token"),
        gitlab_token: str | None = Header(default=None, alias="X-LegacyPilot-GitLab-Token"),
    ) -> GraphSnapshot:
        credentials = _runtime_credentials_from_headers(
            qwen_api_key=qwen_api_key,
            github_token=github_token,
            gitlab_token=gitlab_token,
        )
        with use_runtime_credentials(credentials):
            return middleware_router.index_repo(request)

    @app.post("/v1/graph/query", response_model=GraphContext)
    async def query_graph(query: GraphQuery) -> GraphContext:
        return middleware_router.query_graph(query)

    @app.get("/v1/graphs", response_model=list[StoredGraph])
    async def list_graphs() -> list[StoredGraph]:
        return middleware_router.list_graphs()

    @app.delete("/v1/graphs/{repo_id}/{graph_id}", response_model=DeleteGraphResponse)
    async def delete_graph(repo_id: str, graph_id: str) -> DeleteGraphResponse:
        return middleware_router.delete_graph(repo_id=repo_id, graph_id=graph_id)

    @app.post("/v1/alerts/submit", response_model=IncidentQuery)
    async def submit_alert(alert: AlertEvent) -> IncidentQuery:
        return middleware_router.submit_alert(alert)

    @app.post("/v1/evidence-bundles/build", response_model=EvidenceBundle)
    async def build_evidence_bundle(query: IncidentQuery) -> EvidenceBundle:
        return middleware_router.build_evidence_bundle(query)

    @app.post("/v1/incidents/similar", response_model=list[IncidentMatch])
    async def find_similar_incidents(query: IncidentQuery) -> list[IncidentMatch]:
        return middleware_router.find_similar_incidents(query)

    @app.post("/v1/rca/generate", response_model=RCAReport)
    async def generate_rca(
        bundle: EvidenceBundle,
        qwen_api_key: str | None = Header(default=None, alias="X-LegacyPilot-Qwen-Api-Key"),
    ) -> RCAReport:
        credentials = _runtime_credentials_from_headers(qwen_api_key=qwen_api_key)
        with use_runtime_credentials(credentials):
            return middleware_router.generate_rca(bundle)

    @app.post("/v1/rca/review", response_model=ReviewedRCAReport)
    async def review_rca(report: RCAReport) -> ReviewedRCAReport:
        return middleware_router.review_rca(report)

    @app.post("/v1/incidents/save", response_model=IncidentRecord)
    async def save_incident(request: SaveIncidentRequest) -> IncidentRecord:
        return middleware_router.save_incident(
            reviewed_report=request.reviewed_report,
            user_confirmation=request.user_confirmation,
            fix_outcome=request.fix_outcome,
            retention_policy=request.retention_policy,
            contract_version=request.contract_version,
        )

    @app.get("/v1/incidents/{incident_id}", response_model=IncidentRecord)
    async def load_incident(incident_id: str) -> IncidentRecord:
        return middleware_router.load_incident(incident_id)

    return app


app = create_app()
