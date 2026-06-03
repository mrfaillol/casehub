"""
Tests for tenant isolation - Verify that critical queries always include org_id filtering.

These tests inspect the SQL strings / raw queries used in routes to ensure that
tenant isolation (org_id) is enforced. This prevents data leakage across tenants.
"""
import pytest
import inspect
import re


class TestContactsQueryIsolation:
    """Verify contacts routes include org_id in all queries."""

    def test_contacts_list_query_has_org_id(self):
        from routes.contacts import contacts_list
        source = inspect.getsource(contacts_list)
        assert "org_id" in source, "contacts_list must filter by org_id"

    def test_contacts_search_query_has_org_id(self):
        from routes.contacts import search_contacts
        source = inspect.getsource(search_contacts)
        assert "org_id" in source, "search_contacts must filter by org_id"

    def test_contacts_view_query_has_org_id(self):
        from routes.contacts import view_contact
        source = inspect.getsource(view_contact)
        assert "org_id" in source, "view_contact must filter by org_id"

    def test_contacts_delete_query_has_org_id(self):
        from routes.contacts import delete_contact
        source = inspect.getsource(delete_contact)
        assert "org_id" in source, "delete_contact must filter by org_id"

    def test_contacts_create_query_has_org_id(self):
        from routes.contacts import create_contact
        source = inspect.getsource(create_contact)
        assert "org_id" in source, "create_contact must include org_id"


class TestCustomFieldsQueryIsolation:
    """Verify custom fields routes include org_id in all queries."""

    def test_list_definitions_has_org_id(self):
        from routes.custom_fields import list_definitions
        source = inspect.getsource(list_definitions)
        assert "org_id" in source, "list_definitions must filter by org_id"

    def test_create_definition_has_org_id(self):
        from routes.custom_fields import create_definition
        source = inspect.getsource(create_definition)
        assert "org_id" in source, "create_definition must include org_id"

    def test_edit_definition_has_org_id(self):
        from routes.custom_fields import edit_definition
        source = inspect.getsource(edit_definition)
        assert "org_id" in source, "edit_definition must filter by org_id"

    def test_update_definition_has_org_id(self):
        from routes.custom_fields import update_definition
        source = inspect.getsource(update_definition)
        assert "org_id" in source, "update_definition must filter by org_id"

    def test_delete_definition_has_org_id(self):
        from routes.custom_fields import delete_definition
        source = inspect.getsource(delete_definition)
        assert "org_id" in source, "delete_definition must filter by org_id"

    def test_api_get_definitions_has_org_id(self):
        from routes.custom_fields import api_get_definitions
        source = inspect.getsource(api_get_definitions)
        assert "org_id" in source, "api_get_definitions must filter by org_id"

    def test_api_get_values_has_org_id(self):
        from routes.custom_fields import api_get_values
        source = inspect.getsource(api_get_values)
        assert "org_id" in source, "api_get_values must filter by org_id"


class TestBulkOperationsQueryIsolation:
    """Verify bulk operations routes include org_id in all queries."""

    def test_bulk_dashboard_has_org_id(self):
        from routes.bulk import bulk_dashboard
        source = inspect.getsource(bulk_dashboard)
        assert "org_id" in source, "bulk_dashboard must filter by org_id"

    def test_execute_bulk_cases_has_org_id(self):
        from routes.bulk import execute_bulk_cases
        source = inspect.getsource(execute_bulk_cases)
        assert "org_id" in source, "execute_bulk_cases must filter by org_id"

    def test_execute_bulk_clients_has_org_id(self):
        from routes.bulk import execute_bulk_clients
        source = inspect.getsource(execute_bulk_clients)
        assert "org_id" in source, "execute_bulk_clients must filter by org_id"


class TestInvoiceQueryIsolation:
    """Verify invoice routes include org_id via tenant_query or direct filter."""

    def test_invoices_module_uses_tenant_query(self):
        """Invoice routes should import and use tenant_query for data scoping."""
        from routes import invoices
        source = inspect.getsource(invoices)
        assert "tenant_query" in source or "org_id" in source, \
            "Invoices module must use tenant_query or filter by org_id"


class TestRelationshipsQueryIsolation:
    """Verify relationship queries include org_id."""

    def test_get_relationships_has_org_id(self):
        from routes.contacts import get_relationships
        source = inspect.getsource(get_relationships)
        assert "org_id" in source, "get_relationships must filter by org_id"

    def test_create_relationship_has_org_id(self):
        from routes.contacts import create_relationship
        source = inspect.getsource(create_relationship)
        assert "org_id" in source, "create_relationship must include org_id"

    def test_delete_relationship_has_org_id(self):
        from routes.contacts import delete_relationship
        source = inspect.getsource(delete_relationship)
        assert "org_id" in source, "delete_relationship must filter by org_id"


class TestTenantQueryHelper:
    """Test the tenant_query helper itself."""

    def test_tenant_query_filters_by_org_id(self):
        """tenant_query source should contain model.org_id == org_id filter."""
        from models.tenant import tenant_query
        source = inspect.getsource(tenant_query)
        assert "org_id" in source
        assert "filter" in source

    def test_tenant_count_filters_by_org_id(self):
        from models.tenant import tenant_count
        source = inspect.getsource(tenant_count)
        assert "org_id" in source
        assert "filter" in source
