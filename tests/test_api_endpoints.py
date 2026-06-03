"""
Test API Endpoints for CaseHub REST API (routes/api.py).

Tests the 5 list endpoints (clients, cases, tasks, documents, users),
verifying:
  - Endpoint functions accept the correct parameters
  - Pagination (skip, limit) is passed through
  - Search/filter arguments are handled
  - Tenant isolation via org_id filtering (tenant_query usage)
  - Response dict structure matches expected keys
  - Pydantic models validate correctly
"""
import inspect
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Endpoint signature tests
# ---------------------------------------------------------------------------

class TestListEndpointSignatures:
    """Verify that list endpoints accept the expected parameters."""

    def test_list_clients_has_request_param(self):
        from routes.api import list_clients
        sig = inspect.signature(list_clients)
        assert "request" in sig.parameters

    def test_list_clients_has_skip_param(self):
        from routes.api import list_clients
        sig = inspect.signature(list_clients)
        assert "skip" in sig.parameters

    def test_list_clients_has_limit_param(self):
        from routes.api import list_clients
        sig = inspect.signature(list_clients)
        assert "limit" in sig.parameters

    def test_list_clients_has_search_param(self):
        from routes.api import list_clients
        sig = inspect.signature(list_clients)
        assert "search" in sig.parameters

    def test_list_cases_has_request_param(self):
        from routes.api import list_cases
        sig = inspect.signature(list_cases)
        assert "request" in sig.parameters

    def test_list_cases_has_skip_and_limit(self):
        from routes.api import list_cases
        sig = inspect.signature(list_cases)
        assert "skip" in sig.parameters
        assert "limit" in sig.parameters

    def test_list_cases_has_search_param(self):
        from routes.api import list_cases
        sig = inspect.signature(list_cases)
        assert "search" in sig.parameters

    def test_list_cases_has_status_filter(self):
        from routes.api import list_cases
        sig = inspect.signature(list_cases)
        assert "status" in sig.parameters

    def test_list_cases_has_visa_type_filter(self):
        from routes.api import list_cases
        sig = inspect.signature(list_cases)
        assert "visa_type" in sig.parameters

    def test_list_tasks_has_request_param(self):
        from routes.api import list_tasks
        sig = inspect.signature(list_tasks)
        assert "request" in sig.parameters

    def test_list_tasks_has_pagination(self):
        from routes.api import list_tasks
        sig = inspect.signature(list_tasks)
        assert "skip" in sig.parameters
        assert "limit" in sig.parameters

    def test_list_tasks_has_status_filter(self):
        from routes.api import list_tasks
        sig = inspect.signature(list_tasks)
        assert "status" in sig.parameters

    def test_list_tasks_has_priority_filter(self):
        from routes.api import list_tasks
        sig = inspect.signature(list_tasks)
        assert "priority" in sig.parameters

    def test_list_tasks_has_assigned_to_filter(self):
        from routes.api import list_tasks
        sig = inspect.signature(list_tasks)
        assert "assigned_to" in sig.parameters

    def test_list_documents_has_request_param(self):
        from routes.api import list_documents
        sig = inspect.signature(list_documents)
        assert "request" in sig.parameters

    def test_list_documents_has_pagination(self):
        from routes.api import list_documents
        sig = inspect.signature(list_documents)
        assert "skip" in sig.parameters
        assert "limit" in sig.parameters

    def test_list_documents_has_case_id_filter(self):
        from routes.api import list_documents
        sig = inspect.signature(list_documents)
        assert "case_id" in sig.parameters

    def test_list_users_has_request_param(self):
        from routes.api import list_users
        sig = inspect.signature(list_users)
        assert "request" in sig.parameters

    def test_list_users_has_pagination(self):
        from routes.api import list_users
        sig = inspect.signature(list_users)
        assert "skip" in sig.parameters
        assert "limit" in sig.parameters


# ---------------------------------------------------------------------------
# Tenant isolation (source inspection)
# ---------------------------------------------------------------------------

class TestAPITenantIsolation:
    """Verify that all list endpoints use tenant_query for org scoping."""

    def test_list_clients_uses_tenant_query(self):
        from routes.api import list_clients
        source = inspect.getsource(list_clients)
        assert "tenant_query" in source, "list_clients must use tenant_query"
        assert "org_id" in source, "list_clients must reference org_id"

    def test_list_cases_uses_tenant_query(self):
        from routes.api import list_cases
        source = inspect.getsource(list_cases)
        assert "tenant_query" in source
        assert "org_id" in source

    def test_list_tasks_uses_tenant_query(self):
        from routes.api import list_tasks
        source = inspect.getsource(list_tasks)
        assert "tenant_query" in source
        assert "org_id" in source

    def test_list_documents_uses_tenant_query(self):
        from routes.api import list_documents
        source = inspect.getsource(list_documents)
        assert "tenant_query" in source
        assert "org_id" in source

    def test_list_users_uses_tenant_query(self):
        from routes.api import list_users
        source = inspect.getsource(list_users)
        assert "tenant_query" in source
        assert "org_id" in source

    def test_create_client_assigns_org_id(self):
        """create_client should attach org_id to new records."""
        from routes.api import create_client
        source = inspect.getsource(create_client)
        assert "org_id" in source

    def test_create_case_assigns_org_id(self):
        from routes.api import create_case
        source = inspect.getsource(create_case)
        assert "org_id" in source

    def test_create_task_assigns_org_id(self):
        from routes.api import create_task
        source = inspect.getsource(create_task)
        assert "org_id" in source


# ---------------------------------------------------------------------------
# Dict serializer helpers
# ---------------------------------------------------------------------------

class TestAPIDictSerializers:
    """Verify that the to_dict helper functions return the expected keys."""

    def test_client_to_dict_keys(self):
        from routes.api import client_to_dict
        mock_client = MagicMock()
        mock_client.date_of_birth = None
        mock_client.created_at = None
        mock_client.updated_at = None
        result = client_to_dict(mock_client)
        expected_keys = {
            "id", "first_name", "last_name", "full_name", "email", "phone",
            "whatsapp", "date_of_birth", "country_of_origin", "ssn",
            "alien_number", "passport_number", "address", "status", "notes",
            "created_at", "updated_at",
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_case_to_dict_keys(self):
        from routes.api import case_to_dict
        mock_case = MagicMock()
        mock_case.application_date = None
        mock_case.processing_date = None
        mock_case.expiration_date = None
        mock_case.case_value = None
        mock_case.amount_paid = None
        mock_case.created_at = None
        mock_case.updated_at = None
        result = case_to_dict(mock_case)
        expected_keys = {
            "id", "client_id", "case_number", "case_name", "receipt_number",
            "visa_type", "status", "priority", "notes", "created_at",
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_task_to_dict_keys(self):
        from routes.api import task_to_dict
        mock_task = MagicMock()
        mock_task.due_date = None
        mock_task.completed_at = None
        mock_task.created_at = None
        result = task_to_dict(mock_task)
        expected_keys = {
            "id", "title", "description", "case_id", "client_id",
            "task_type", "status", "priority", "assigned_to", "due_date",
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_document_to_dict_keys(self):
        from routes.api import document_to_dict
        mock_doc = MagicMock()
        mock_doc.expiration_date = None
        mock_doc.created_at = None
        result = document_to_dict(mock_doc)
        expected_keys = {
            "id", "client_id", "case_id", "name", "document_type",
            "status", "file_path", "file_size", "mime_type", "notes",
        }
        assert expected_keys.issubset(set(result.keys()))


# ---------------------------------------------------------------------------
# Pydantic model validation
# ---------------------------------------------------------------------------

class TestAPIPydanticModels:
    """Test that Pydantic request models validate correctly."""

    def test_client_create_minimal(self):
        from routes.api import ClientCreate
        client = ClientCreate(first_name="Jane", last_name="Doe")
        assert client.first_name == "Jane"
        assert client.email is None

    def test_client_create_full(self):
        from routes.api import ClientCreate
        client = ClientCreate(
            first_name="Jane", last_name="Doe",
            email="jane@example.com", phone="+1234567890",
            status="active",
        )
        assert client.email == "jane@example.com"
        assert client.status == "active"

    def test_client_create_missing_required_raises(self):
        from routes.api import ClientCreate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ClientCreate(first_name="Jane")  # missing last_name

    def test_case_create_minimal(self):
        from routes.api import CaseCreate
        case = CaseCreate(client_id=1)
        assert case.client_id == 1
        assert case.status == "intake"
        assert case.priority == "medium"

    def test_task_create_minimal(self):
        from routes.api import TaskCreate
        task = TaskCreate(title="File motion")
        assert task.title == "File motion"
        assert task.status == "todo"

    def test_task_create_missing_title_raises(self):
        from routes.api import TaskCreate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TaskCreate(description="no title")

    def test_client_update_partial(self):
        from routes.api import ClientUpdate
        update = ClientUpdate(email="new@example.com")
        dumped = update.model_dump(exclude_unset=True)
        assert "email" in dumped
        assert "first_name" not in dumped

    def test_case_update_partial(self):
        from routes.api import CaseUpdate
        update = CaseUpdate(status="approved")
        dumped = update.model_dump(exclude_unset=True)
        assert dumped == {"status": "approved"}
