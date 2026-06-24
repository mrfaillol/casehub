// Google Drive Picker Configuration
      // Configured for CaseHub Case Management
      // SECURITY: this file is served to the browser as a static asset, so it CANNOT
      // receive server-side template injection. NEVER hardcode an API key / client id here.
      // The host page must set window.GOOGLE_CONFIG = { apiKey, clientId, appId } from an
      // env-injected template before this script runs. The Picker browser key MUST be
      // HTTP-referrer restricted in the Google Cloud Console.
      const GOOGLE_API_KEY = (window.GOOGLE_CONFIG && window.GOOGLE_CONFIG.apiKey) || '';
      const GOOGLE_CLIENT_ID = (window.GOOGLE_CONFIG && window.GOOGLE_CONFIG.clientId) || '';
      const GOOGLE_APP_ID = (window.GOOGLE_CONFIG && window.GOOGLE_CONFIG.appId) || "152327852610";
      const SCOPES = "https://www.googleapis.com/auth/drive.readonly";

      let googlePickerInited = false;
      let gisInited = false;
      let googleAccessToken = null;

      // Initialize Google API
      function gapiLoaded() {
        gapi.load("picker", () => {
          googlePickerInited = true;
        });
      }

      function gisLoaded() {
        gisInited = true;
      }

      // Load Google APIs on page load
      if (typeof gapi !== "undefined") {
        gapiLoaded();
      }
      if (typeof google !== "undefined" && google.accounts) {
        gisLoaded();
      }

// ===========================================
      // Editable Dropdowns
      // ===========================================

      // Load custom options and restore state on page load
      document.addEventListener("DOMContentLoaded", function () {
        loadCustomOptions();
        restoreSection();
        restoreFormData();
        setupFormPersistence();
      });

      // ===========================================
      // Form Data Persistence
      // ===========================================
      const FORM_STORAGE_KEY = 'ilc_form_data';

      function saveFormData() {
        const formData = {};

        // LOR Form fields
        const lorForm = document.getElementById('lor-form');
        if (lorForm) {
          formData.lor = {};
          lorForm.querySelectorAll('input, select, textarea').forEach(el => {
            if (el.name || el.id) {
              const key = el.name || el.id;
              if (el.type === 'checkbox') {
                formData.lor[key] = el.checked;
              } else if (el.type === 'file') {
                // Skip file inputs
              } else {
                formData.lor[key] = el.value;
              }
            }
          });
          // Save selected persona
          const selectedPersona = document.querySelector('.persona-card.selected');
          if (selectedPersona) {
            formData.lor.selectedPersona = selectedPersona.dataset.persona;
          }
        }

        // PS Form fields
        const psForm = document.getElementById('ps-form');
        if (psForm) {
          formData.ps = {};
          psForm.querySelectorAll('input, select, textarea').forEach(el => {
            if (el.name || el.id) {
              const key = el.name || el.id;
              if (el.type === 'checkbox') {
                formData.ps[key] = el.checked;
              } else if (el.type === 'file') {
                // Skip file inputs
              } else {
                formData.ps[key] = el.value;
              }
            }
          });
        }

        localStorage.setItem(FORM_STORAGE_KEY, JSON.stringify(formData));
      }

      function restoreFormData() {
        const saved = localStorage.getItem(FORM_STORAGE_KEY);
        if (!saved) return;

        try {
          const formData = JSON.parse(saved);

          // Restore LOR Form
          if (formData.lor) {
            Object.keys(formData.lor).forEach(key => {
              if (key === 'selectedPersona') {
                // Restore persona selection
                const personaCard = document.querySelector(`.persona-card[data-persona="${formData.lor[key]}"]`);
                if (personaCard) {
                  selectPersona(personaCard);
                }
              } else {
                const el = document.getElementById(key) || document.querySelector(`[name="${key}"]`);
                if (el) {
                  if (el.type === 'checkbox') {
                    el.checked = formData.lor[key];
                  } else {
                    el.value = formData.lor[key];
                  }
                }
              }
            });
          }

          // Restore PS Form
          if (formData.ps) {
            Object.keys(formData.ps).forEach(key => {
              const el = document.getElementById(key) || document.querySelector(`[name="${key}"]`);
              if (el) {
                if (el.type === 'checkbox') {
                  el.checked = formData.ps[key];
                } else {
                  el.value = formData.ps[key];
                }
              }
            });
          }
        } catch (e) {
          console.error('Error restoring form data:', e);
        }
      }

      function setupFormPersistence() {
        // Auto-save on input change with debounce
        let saveTimeout;
        const debouncedSave = () => {
          clearTimeout(saveTimeout);
          saveTimeout = setTimeout(saveFormData, 500);
        };

        // Listen to all form inputs
        document.querySelectorAll('#lor-form input, #lor-form select, #lor-form textarea').forEach(el => {
          el.addEventListener('input', debouncedSave);
          el.addEventListener('change', debouncedSave);
        });

        document.querySelectorAll('#ps-form input, #ps-form select, #ps-form textarea').forEach(el => {
          el.addEventListener('input', debouncedSave);
          el.addEventListener('change', debouncedSave);
        });

        // Also save when persona is selected
        document.querySelectorAll('.persona-card').forEach(card => {
          card.addEventListener('click', () => setTimeout(saveFormData, 100));
        });
      }

      // Clear form data after successful submission (optional - call this in generateLOR/generatePS if desired)
      function clearFormData(formType) {
        const saved = localStorage.getItem(FORM_STORAGE_KEY);
        if (saved) {
          const formData = JSON.parse(saved);
          if (formType && formData[formType]) {
            delete formData[formType];
            localStorage.setItem(FORM_STORAGE_KEY, JSON.stringify(formData));
          }
        }
      }

      function loadCustomOptions() {
        const customOptions = JSON.parse(
          localStorage.getItem("ilc_custom_options") || "{}"
        );

        // Load for each dropdown type
        Object.keys(customOptions).forEach((type) => {
          const options = customOptions[type] || [];
          options.forEach((opt) => {
            addOptionToAllSelects(type, opt.value, opt.label);
          });
        });
      }

      function addOptionToAllSelects(type, value, label) {
        // Find all selects that match this type
        let selectors = [];
        if (type === "visa_type") {
          selectors = ["#visa_type"];
        } else if (type === "field") {
          selectors = ["#lor_field", "#ps_field"];
        } else if (type === "relationship") {
          selectors = ["#relationship"];
        } else if (type === "ps_section1") {
          selectors = ["#ps_section1"];
        } else if (type === "ps_section2") {
          selectors = ["#ps_section2"];
        } else if (type === "ps_section3") {
          selectors = ["#ps_section3"];
        } else if (type === "ps_section4") {
          selectors = ["#ps_section4"];
        } else if (type === "ps_section5") {
          selectors = ["#ps_section5"];
        }

        selectors.forEach((selector) => {
          const select = document.querySelector(selector);
          if (select) {
            // Check if option already exists
            const exists = Array.from(select.options).some(
              (opt) => opt.value === value
            );
            if (!exists) {
              // Insert before "Add New" option
              const addNewOption = select.querySelector(
                'option[value="__add_new__"]'
              );
              const newOption = document.createElement("option");
              newOption.value = value;
              newOption.textContent = label;
              newOption.className = "custom-option";
              select.insertBefore(newOption, addNewOption);
            }
          }
        });
      }

      function handleSelectChange(selectElement, type) {
        if (selectElement.value === "__add_new__") {
          // Show the add new input
          const addInput = document.getElementById("add-" + selectElement.id);
          if (addInput) {
            addInput.classList.add("visible");
            addInput.querySelector("input").focus();
          }
          // Reset to previous value or first option
          selectElement.selectedIndex = 0;
        }
      }

      function addNewOption(selectId) {
        const select = document.getElementById(selectId);
        const addInputDiv = document.getElementById("add-" + selectId);
        const input = addInputDiv.querySelector("input");
        const value = input.value.trim();

        if (!value) {
          alert("Please enter a value");
          return;
        }

        // Determine the type for storage
        let type = selectId;
        if (selectId === "lor_field" || selectId === "ps_field") {
          type = "field";
        }

        // Create slug-like value
        const slugValue = value.toLowerCase().replace(/[^a-z0-9]+/g, "_");

        // Add to select
        addOptionToAllSelects(type, slugValue, value);

        // Save to localStorage
        const customOptions = JSON.parse(
          localStorage.getItem("ilc_custom_options") || "{}"
        );
        if (!customOptions[type]) {
          customOptions[type] = [];
        }

        // Check if already exists
        if (!customOptions[type].some((opt) => opt.value === slugValue)) {
          customOptions[type].push({ value: slugValue, label: value });
          localStorage.setItem(
            "ilc_custom_options",
            JSON.stringify(customOptions)
          );
        }

        // Select the new option
        select.value = slugValue;

        // Hide input and clear
        addInputDiv.classList.remove("visible");
        input.value = "";
      }

      function cancelAddNew(selectId) {
        const addInputDiv = document.getElementById("add-" + selectId);
        addInputDiv.classList.remove("visible");
        addInputDiv.querySelector("input").value = "";
      }

      // ===========================================
      // Navigation with persistence
      // ===========================================
      function showSection(section, updateHistory = true) {
        // Hide all sections
        document
          .querySelectorAll(".section")
          .forEach((s) => s.classList.remove("active"));

        // Deactivate all nav buttons
        document
          .querySelectorAll("nav button")
          .forEach((b) => b.classList.remove("active"));

        // Show target section
        const sectionEl = document.getElementById(section + "-section");
        if (sectionEl) sectionEl.classList.add("active");

        // Activate target button
        const btnEl = document.getElementById("nav-btn-" + section);
        if (btnEl) btnEl.classList.add("active");

        // Persist section in URL hash and localStorage
        if (updateHistory) {
          window.location.hash = section;
          localStorage.setItem('ilc_current_section', section);
        }
      }

      // Restore section from URL hash or localStorage on page load
      function restoreSection() {
        let section = 'dashboard'; // default

        // Priority: URL hash > localStorage
        if (window.location.hash) {
          section = window.location.hash.substring(1);
        } else {
          const saved = localStorage.getItem('ilc_current_section');
          if (saved) section = saved;
        }

        // Validate section exists
        const validSections = ['dashboard', 'lor', 'ps', 'package', 'pdf', 'clients', 'docs', 'tasks', 'agenda'];
        if (!validSections.includes(section)) section = 'dashboard';

        showSection(section, false);
      }

      // Handle browser back/forward navigation
      window.addEventListener('hashchange', function() {
        const section = window.location.hash.substring(1);
        if (section) showSection(section, false);
      });

      // ===========================================
      // CLIENT MANAGEMENT (Email Processor)
      // ===========================================

      let clientsData = [];
      let editingClientEmail = null;
      let clientsLoaded = false;

      // Tab switching
      function showClientsTab(tab) {
        document.getElementById('tab-email-clients').classList.toggle('active', tab === 'email');
        document.getElementById('tab-sheets').classList.toggle('active', tab === 'sheets');
        document.getElementById('email-clients-tab').style.display = tab === 'email' ? 'block' : 'none';
        document.getElementById('sheets-tab').style.display = tab === 'sheets' ? 'block' : 'none';

        if (tab === 'email' && !clientsLoaded) {
          loadEmailProcessorClients();
        }
      }

      // Load clients from API
      async function loadEmailProcessorClients() {
        const loadingEl = document.getElementById('clients-loading');
        const tableContainer = document.getElementById('clients-table-container');
        const emptyEl = document.getElementById('clients-empty');

        loadingEl.style.display = 'block';
        tableContainer.style.display = 'none';
        emptyEl.style.display = 'none';

        try {
          const token = localStorage.getItem('ilc_access_token');
          const response = await fetch('/api/email-processor/clients', {
            headers: token ? { 'Authorization': `Bearer ${token}` } : {}
          });

          if (response.ok) {
            const data = await response.json();
            clientsData = data.clients || [];
            clientsLoaded = true;
            renderClientsTable();
            updateClientsStats();
          } else if (response.status === 401) {
            loadingEl.innerHTML = '<p style="color: var(--text-secondary);">Session expired. Please <a href="/login" style="color: var(--accent);">login again</a>.</p>';
          } else {
            throw new Error('Failed to load clients');
          }
        } catch (error) {
          console.error('Clients error:', error);
          loadingEl.innerHTML = '<p style="color: var(--error);">Error loading clients. Check console for details.</p>';
        }
      }

      // Render clients table
      function renderClientsTable() {
        const loadingEl = document.getElementById('clients-loading');
        const tableContainer = document.getElementById('clients-table-container');
        const emptyEl = document.getElementById('clients-empty');
        const tbody = document.getElementById('clients-tbody');

        loadingEl.style.display = 'none';

        if (clientsData.length === 0) {
          emptyEl.style.display = 'block';
          tableContainer.style.display = 'none';
          return;
        }

        tableContainer.style.display = 'block';
        tbody.innerHTML = clientsData.map(client => renderClientRow(client)).join('');
      }

      // Render single client row
      function renderClientRow(client) {
        const paralegalClass = client.paralegal.toLowerCase().replace(' ', '-');
        const escapedEmail = escapeHtml(client.email);
        return `
          <tr data-email="${escapedEmail}">
            <td>
              <div class="cell-content">${escapeHtml(client.name) || '<span style="color: var(--text-muted);">No name</span>'}</div>
            </td>
            <td>
              <div class="cell-content" style="font-family: monospace; font-size: 0.85rem;">${escapedEmail}</div>
            </td>
            <td>
              <div class="cell-content">${client.case || '<span style="color: var(--text-muted);">-</span>'}</div>
            </td>
            <td class="paralegal-cell" onclick="editClientParalegal(this, '${escapedEmail}')" style="cursor: pointer;" title="Click to change">
              <span class="paralegal-badge ${paralegalClass}">${escapeHtml(client.paralegal)}</span>
            </td>
            <td style="text-align: center;">
              <button class="delete-btn" onclick="event.stopPropagation(); deleteClient('${escapedEmail}')" title="Remove client">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                </svg>
              </button>
            </td>
          </tr>
        `;
      }

      // Edit paralegal inline
      function editClientParalegal(td, email) {
        const client = clientsData.find(c => c.email === email);
        if (!client) return;

        td.innerHTML = `
          <select onchange="saveClientParalegal('${email}', this.value)" onblur="setTimeout(() => cancelClientEdit('${email}'), 200)">
            <option value="Membro B" ${client.paralegal === 'Membro B' ? 'selected' : ''}>Membro B</option>
            <option value="Membro A" ${client.paralegal === 'Membro A' ? 'selected' : ''}>Membro A</option>
          </select>
        `;
        td.querySelector('select').focus();
      }

      // Save paralegal change
      async function saveClientParalegal(email, newParalegal) {
        try {
          const token = localStorage.getItem('ilc_access_token');
          const response = await fetch(`/api/email-processor/clients/${encodeURIComponent(email)}`, {
            method: 'PUT',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ paralegal: newParalegal })
          });

          if (response.ok) {
            // Update local data
            const client = clientsData.find(c => c.email === email);
            if (client) client.paralegal = newParalegal;
            renderClientsTable();
            updateClientsStats();
            showToast('Client updated successfully', 'success');
          } else {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to update client');
          }
        } catch (error) {
          console.error('Update error:', error);
          showToast('Error: ' + error.message, 'error');
          renderClientsTable();
        }
      }

      // Cancel edit
      function cancelClientEdit(email) {
        renderClientsTable();
      }

      // Update stats
      function updateClientsStats() {
        document.getElementById('total-clients').textContent = clientsData.length;
        const memberBCount = document.getElementById('member-b-count');
        const memberACount = document.getElementById('member-a-count');
        if (memberBCount) memberBCount.textContent = clientsData.filter(c => c.paralegal === 'Membro B').length;
        if (memberACount) memberACount.textContent = clientsData.filter(c => c.paralegal === 'Membro A').length;
      }

      // Filter clients table
      function filterClientsTable() {
        const filter = document.getElementById('clients-search').value.toLowerCase();
        const rows = document.querySelectorAll('#clients-tbody tr');

        rows.forEach(row => {
          const text = row.textContent.toLowerCase();
          row.style.display = text.includes(filter) ? '' : 'none';
        });
      }

      // Modal functions
      function showAddClientModal() {
        editingClientEmail = null;
        document.getElementById('client-modal-title').textContent = 'Add New Client';
        document.getElementById('client-form').reset();
        document.getElementById('client-email').disabled = false;
        document.getElementById('client-modal').style.display = 'flex';
      }

      function editClientFull(email) {
        const client = clientsData.find(c => c.email === email);
        if (!client) return;

        editingClientEmail = email;
        document.getElementById('client-modal-title').textContent = 'Edit Client';
        document.getElementById('client-name').value = client.name;
        document.getElementById('client-email').value = client.email;
        document.getElementById('client-email').disabled = true;
        document.getElementById('client-case').value = client.case || '';
        document.getElementById('client-paralegal').value = client.paralegal;
        document.getElementById('client-modal').style.display = 'flex';
      }

      function closeClientModal() {
        document.getElementById('client-modal').style.display = 'none';
        editingClientEmail = null;
      }

      // Save client (add or edit)
      async function saveClient(event) {
        event.preventDefault();

        const formData = {
          name: document.getElementById('client-name').value,
          email: document.getElementById('client-email').value,
          case: document.getElementById('client-case').value,
          paralegal: document.getElementById('client-paralegal').value
        };

        try {
          const token = localStorage.getItem('ilc_access_token');
          const url = editingClientEmail
            ? `/api/email-processor/clients/${encodeURIComponent(editingClientEmail)}`
            : '/api/email-processor/clients';
          const method = editingClientEmail ? 'PUT' : 'POST';

          const response = await fetch(url, {
            method,
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(formData)
          });

          if (response.ok) {
            closeClientModal();
            clientsLoaded = false;
            loadEmailProcessorClients();
            showToast(editingClientEmail ? 'Client updated' : 'Client added successfully', 'success');
          } else {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save client');
          }
        } catch (error) {
          console.error('Save error:', error);
          showToast('Error: ' + error.message, 'error');
        }
      }

      // Delete client
      async function deleteClient(email) {
        if (!confirm(`Remove client "${email}" from email processor?\n\nThis will stop notifications for this client.`)) return;

        try {
          const token = localStorage.getItem('ilc_access_token');
          const response = await fetch(`/api/email-processor/clients/${encodeURIComponent(email)}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
          });

          if (response.ok) {
            clientsLoaded = false;
            loadEmailProcessorClients();
            showToast('Client removed', 'success');
          } else {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to remove client');
          }
        } catch (error) {
          console.error('Delete error:', error);
          showToast('Error: ' + error.message, 'error');
        }
      }

      // Toast notification helper
      function showToast(message, type = 'info') {
        // Remove any existing toasts
        document.querySelectorAll('.toast').forEach(t => t.remove());

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
      }

      // Helper to escape HTML
      function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
      }

      // Override showSection to load clients when navigating to clients section
      const _originalShowSection = showSection;
      showSection = function(section, updateHistory = true) {
        _originalShowSection(section, updateHistory);
        if (section === 'clients' && !clientsLoaded) {
          loadEmailProcessorClients();
        }
      };

      // Persona selection
      function selectPersona(element) {
        document
          .querySelectorAll(".persona-card")
          .forEach((c) => c.classList.remove("selected"));
        element.classList.add("selected");
        document.getElementById("persona").value = element.dataset.persona;
      }

      // ===========================================
      // CUSTOM PROFILE ANALYZER
      // ===========================================

      // Storage key for custom profiles
      const CUSTOM_PROFILES_KEY = "ilc_custom_profiles";

      // Load custom profiles from localStorage
      function loadCustomProfiles() {
        const stored = localStorage.getItem(CUSTOM_PROFILES_KEY);
        return stored ? JSON.parse(stored) : [];
      }

      // Save custom profiles to localStorage
      function saveCustomProfiles(profiles) {
        localStorage.setItem(CUSTOM_PROFILES_KEY, JSON.stringify(profiles));
      }

      // Toggle custom profile form visibility
      function toggleCustomProfileForm() {
        const form = document.getElementById("custom-profile-form");
        form.style.display = form.style.display === "none" ? "block" : "none";
      }

      // Render custom personas in the grid
      function renderCustomPersonas() {
        const profiles = loadCustomProfiles();
        const container = document.getElementById("custom-personas-container");
        const grid = document.getElementById("custom-personas-grid");

        if (profiles.length === 0) {
          container.style.display = "none";
          return;
        }

        container.style.display = "block";
        grid.innerHTML = "";

        profiles.forEach((profile, index) => {
          const card = document.createElement("div");
          card.className = "persona-card";
          card.dataset.persona = `custom_${index}`;
          card.dataset.customProfile = JSON.stringify(profile);
          card.onclick = function () {
            selectCustomPersona(this, profile);
          };
          card.innerHTML = `
                    <div class="persona-name">${profile.name}</div>
                    <div class="persona-font">${profile.font} ${profile.font_size}pt</div>
                    <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.25rem;">${profile.tone}</div>
                    <button type="button" onclick="event.stopPropagation(); deleteCustomProfile(${index});"
                            style="position: absolute; top: 4px; right: 4px; background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.8rem;">×</button>
                `;
          card.style.position = "relative";
          grid.appendChild(card);
        });
      }

      // Select a custom persona
      function selectCustomPersona(element, profile) {
        document
          .querySelectorAll(".persona-card")
          .forEach((c) => c.classList.remove("selected"));
        element.classList.add("selected");

        // Store custom profile data for LOR generation
        document.getElementById("persona").value = "custom";
        window.selectedCustomProfile = profile;
      }

      // Delete a custom profile
      function deleteCustomProfile(index) {
        const profiles = loadCustomProfiles();
        profiles.splice(index, 1);
        saveCustomProfiles(profiles);
        renderCustomPersonas();
      }

      // Analyze profile via server
      async function analyzeProfile() {
        const name = document.getElementById("custom-rec-name").value.trim();
        const title = document.getElementById("custom-rec-title").value.trim();
        const org = document.getElementById("custom-rec-org").value.trim();
        const description = document
          .getElementById("custom-rec-description")
          .value.trim();
        const cvFile = document.getElementById("custom-rec-cv").files[0];

        if (!name) {
          showMessage(
            "profile-analysis-status",
            "error",
            "Recommender name is required"
          );
          document.getElementById("profile-analysis-status").style.color =
            "#e74c3c";
          return;
        }

        const statusEl = document.getElementById("profile-analysis-status");
        const btn = document.getElementById("analyze-btn");

        statusEl.textContent = "Analyzing professional background...";
        statusEl.style.color = "var(--text-muted)";
        btn.disabled = true;
        btn.textContent = "Analyzing...";

        try {
          const formData = new FormData();
          formData.append("name", name);
          formData.append("title", title);
          formData.append("organization", org);
          formData.append("style_description", description);
          if (cvFile) {
            formData.append("cv_file", cvFile);
          }

          const response = await fetch("/api/persona/analyze", {
            method: "POST",
            body: formData,
          });

          const data = await response.json();

          if (data.success && data.persona) {
            // Save to localStorage
            const profiles = loadCustomProfiles();
            profiles.push(data.persona);
            saveCustomProfiles(profiles);

            // Re-render
            renderCustomPersonas();

            // Clear form and hide
            document.getElementById("custom-rec-name").value = "";
            document.getElementById("custom-rec-title").value = "";
            document.getElementById("custom-rec-org").value = "";
            document.getElementById("custom-rec-description").value = "";
            document.getElementById("custom-rec-cv").value = "";
            toggleCustomProfileForm();

            statusEl.textContent = "";
            showMessage(
              "lor-message",
              "success",
              `Profile created: ${data.persona.name}`
            );
          } else {
            statusEl.textContent =
              "Analysis failed: " + (data.error || "Unknown error");
            statusEl.style.color = "#e74c3c";
          }
        } catch (error) {
          statusEl.textContent = "Error: " + error.message;
          statusEl.style.color = "#e74c3c";
        } finally {
          btn.disabled = false;
          btn.textContent = "Analyze & Create Profile";
        }
      }

      // Initialize custom personas on page load
      document.addEventListener("DOMContentLoaded", function () {
        renderCustomPersonas();
      });

      // Toggle Advanced LOR options
      function toggleAdvancedLOR() {
        const options = document.getElementById("advanced-lor-options");
        const toggle = document.getElementById("advanced-lor-toggle");
        if (options.style.display === "none") {
          options.style.display = "block";
          toggle.textContent = "[- Collapse]";
        } else {
          options.style.display = "none";
          toggle.textContent = "[+ Expand]";
        }
      }

      // File list update
      function updateFileList(input, listId) {
        const list = document.getElementById(listId);
        list.innerHTML = "";

        for (const file of input.files) {
          const item = document.createElement("div");
          item.className = "file-item";
          item.innerHTML = `
                    <span>${file.name}</span>
                    <span>${(file.size / 1024).toFixed(1)} KB</span>
                `;
          list.appendChild(item);
        }
      }

      // Show message
      function showMessage(elementId, type, text, downloadUrl = null) {
        const msg = document.getElementById(elementId);
        msg.className = "message " + type;
        msg.innerHTML = text;

        if (downloadUrl) {
          msg.innerHTML += `<br><a href="${downloadUrl}" class="download-link" download>Download File</a>`;
        }
      }

      // Generate LOR
      async function generateLOR(event) {
        event.preventDefault();

        const form = event.target;
        const loading = document.getElementById("lor-loading");
        const formData = new FormData(form);

        // Handle checkboxes
        formData.set(
          "include_national_importance",
          document.getElementById("ni").checked
        );
        formData.set("include_prong3", document.getElementById("p3").checked);

        loading.classList.add("active");
        form.querySelector("button").disabled = true;

        try {
          const response = await fetch("/api/lor/generate", {
            method: "POST",
            body: formData,
          });

          const result = await response.json();

          if (result.success) {
            showMessage(
              "lor-message",
              "success",
              `LOR generated successfully: ${result.filename}`,
              result.download_url
            );
          } else {
            showMessage("lor-message", "error", `Error: ${result.error}`);
          }
        } catch (error) {
          showMessage("lor-message", "error", `Error: ${error.message}`);
        } finally {
          loading.classList.remove("active");
          form.querySelector("button").disabled = false;
        }
      }

      // Generate PS
      async function generatePS(event) {
        event.preventDefault();

        const form = event.target;
        const loading = document.getElementById("ps-loading");
        const formData = new FormData(form);

        loading.classList.add("active");
        form.querySelector("button").disabled = true;

        try {
          const response = await fetch("/api/ps/generate", {
            method: "POST",
            body: formData,
          });

          const result = await response.json();

          if (result.success) {
            showMessage(
              "ps-message",
              "success",
              `Personal Statement generated: ${result.filename}`,
              result.download_url
            );
          } else {
            showMessage("ps-message", "error", `Error: ${result.error}`);
          }
        } catch (error) {
          showMessage("ps-message", "error", `Error: ${error.message}`);
        } finally {
          loading.classList.remove("active");
          form.querySelector("button").disabled = false;
        }
      }

      // Merge Files
      async function mergeFiles(event) {
        event.preventDefault();

        const files = document.getElementById("merge-files").files;
        if (files.length < 1) {
          showMessage("pdf-message", "error", "Please select at least 1 file");
          return;
        }

        const loading = document.getElementById("pdf-loading");
        const formData = new FormData();
        for (const file of files) {
          formData.append("files", file);
        }

        loading.classList.add("active");

        try {
          const response = await fetch("/api/pdf/merge", {
            method: "POST",
            body: formData,
          });

          const result = await response.json();

          if (result.success) {
            showMessageWithPreview(
              "pdf-message",
              "success",
              `Files merged: ${result.filename}`,
              result.download_url
            );
          } else {
            showMessage("pdf-message", "error", `Error: ${result.error}`);
          }
        } catch (error) {
          showMessage("pdf-message", "error", `Error: ${error.message}`);
        } finally {
          loading.classList.remove("active");
        }
      }

      // Images to PDF
      async function imagesToPDF(event) {
        event.preventDefault();

        const files = document.getElementById("image-files").files;
        if (files.length === 0) {
          showMessage(
            "pdf-message",
            "error",
            "Please select at least 1 image file"
          );
          return;
        }

        const loading = document.getElementById("pdf-loading");
        const formData = new FormData();
        for (const file of files) {
          formData.append("files", file);
        }

        loading.classList.add("active");

        try {
          const response = await fetch("/api/pdf/images-to-pdf", {
            method: "POST",
            body: formData,
          });

          const result = await response.json();

          if (result.success) {
            showMessageWithPreview(
              "pdf-message",
              "success",
              `Images converted: ${result.filename}`,
              result.download_url
            );
          } else {
            showMessage("pdf-message", "error", `Error: ${result.error}`);
          }
        } catch (error) {
          showMessage("pdf-message", "error", `Error: ${error.message}`);
        } finally {
          loading.classList.remove("active");
        }
      }

      // Show message with Preview button
      function showMessageWithPreview(elementId, type, message, downloadUrl) {
        const element = document.getElementById(elementId);
        element.className = `message ${type}`;
        element.innerHTML = `
                ${message}
                <div style="margin-top: 0.5rem;">
                    <a href="${downloadUrl}" class="btn" style="margin-right: 0.5rem; text-decoration: none;">Download</a>
                    <button type="button" class="btn btn-secondary" onclick="previewFromUrl('${downloadUrl}')">Preview</button>
                </div>
            `;
        element.style.display = "block";
      }

      async function previewFromUrl(url) {
        try {
          const response = await fetch(url);
          if (!response.ok) throw new Error("Failed to fetch PDF");
          const blob = await response.blob();
          await loadPdfToolsPreview(blob);
        } catch (error) {
          console.error("Preview error:", error);
          showMessage(
            "pdf-message",
            "error",
            "Failed to load preview: " + error.message
          );
        }
      }

      // ===========================================
      // Package Maker
      // ===========================================

      // Exhibit definitions
      const EXHIBITS = {
        A: { name: "Forms", desc: "I-140, ETA-9089, G-1145, G-28" },
        B: {
          name: "Brief",
          desc: "Cover letter, Table of Contents, Legal Brief",
        },
        C: {
          name: "Self Petitioner Info",
          desc: "CV, diplomas, certifications, Personal Statement",
        },
        D: { name: "Critical Role (LORs)", desc: "Letters of Recommendation" },
        E: { name: "High Salary", desc: "W-2, pay stubs, offer letters" },
        F: {
          name: "Memberships",
          desc: "IEEE, ASME, professional associations",
        },
        G: { name: "Judging Work", desc: "Peer review, committee roles" },
        H: {
          name: "Acknowledgements",
          desc: "Citations, acknowledgments in publications",
        },
        I: { name: "Recognition", desc: "Awards, honors, recognitions" },
        J: { name: "Job Offers", desc: "Employment letters, contracts" },
        K: { name: "Media Coverage", desc: "Press articles, interviews" },
        L: {
          name: "Original Contributions",
          desc: "Patents, publications, innovations",
        },
        M: {
          name: "Supporting Research",
          desc: "Government docs, statistics, citations",
        },
      };

      // Package state
      let packageState = {
        currentExhibit: "A",
        exhibits: {},
      };

      // Initialize exhibits
      Object.keys(EXHIBITS).forEach((letter) => {
        packageState.exhibits[letter] = {
          files: [],
          separator: null,
        };
      });

      function selectExhibit(letter) {
        packageState.currentExhibit = letter;

        // Update UI
        document.querySelectorAll(".exhibit-item").forEach((item) => {
          item.classList.remove("selected");
          if (item.dataset.exhibit === letter) {
            item.classList.add("selected");
          }
        });

        // Update content panel
        document.getElementById(
          "current-exhibit-title"
        ).textContent = `Exhibit ${letter} - ${EXHIBITS[letter].name}`;
        document.getElementById("current-exhibit-desc").textContent =
          EXHIBITS[letter].desc;

        // Update separator preview defaults
        document.getElementById("sep-title").value = `EXHIBIT ${letter}`;
        document.getElementById("sep-subtitle").value = EXHIBITS[letter].name;
        updateSeparatorPreview();

        // Update document list
        renderExhibitDocuments();

        // Update checklist
        renderExhibitChecklist(letter);
      }

      function handleExhibitUpload(input) {
        const letter = packageState.currentExhibit;
        const files = Array.from(input.files);

        files.forEach((file) => {
          packageState.exhibits[letter].files.push({
            id: Date.now() + Math.random(),
            file: file,
            name: file.name,
            size: file.size,
            type: "document",
          });
        });

        // Update count
        updateExhibitCount(letter);
        renderExhibitDocuments();

        // Clear input
        input.value = "";
      }

      function updateExhibitCount(letter) {
        const count = packageState.exhibits[letter].files.length;
        const hasSeparator = packageState.exhibits[letter].separator ? 1 : 0;
        const total = count + hasSeparator;

        const item = document.querySelector(
          `.exhibit-item[data-exhibit="${letter}"]`
        );
        if (item) {
          item.querySelector(".exhibit-count").textContent = `${total} files`;
          if (total > 0) {
            item.classList.add("has-files");
          } else {
            item.classList.remove("has-files");
          }
        }
      }

      function renderExhibitDocuments() {
        const letter = packageState.currentExhibit;
        const exhibit = packageState.exhibits[letter];
        const container = document.getElementById("exhibit-documents");

        if (exhibit.files.length === 0 && !exhibit.separator) {
          container.innerHTML =
            '<p style="color: var(--text-secondary); text-align: center; padding: 1rem;">No documents uploaded yet</p>';
          return;
        }

        let html = "";

        // Separator first
        if (exhibit.separator) {
          html += `
                    <div class="document-item" style="background-color: rgba(255,255,255,0.1); border-left: 3px solid var(--accent);">
                        <span class="drag-handle">&#x2630;</span>
                        <span class="doc-name"><strong>SEPARATOR:</strong> ${exhibit.separator.title}</span>
                        <button class="remove-doc" onclick="removeSeparator()" title="Remove">&#x2715;</button>
                    </div>
                `;
        }

        // Documents
        exhibit.files.forEach((doc, index) => {
          html += `
                    <div class="document-item" data-index="${index}">
                        <span class="drag-handle">&#x2630;</span>
                        <span class="doc-name">${doc.name}</span>
                        <span class="doc-size">${(doc.size / 1024).toFixed(
                          1
                        )} KB</span>
                        <button class="remove-doc" onclick="removeDocument(${index})" title="Remove">&#x2715;</button>
                    </div>
                `;
        });

        container.innerHTML = html;
      }

      function removeDocument(index) {
        const letter = packageState.currentExhibit;
        packageState.exhibits[letter].files.splice(index, 1);
        updateExhibitCount(letter);
        renderExhibitDocuments();
      }

      function removeSeparator() {
        const letter = packageState.currentExhibit;
        packageState.exhibits[letter].separator = null;
        updateExhibitCount(letter);
        renderExhibitDocuments();
      }

      function updateSeparatorPreview() {
        const title = document.getElementById("sep-title").value || "EXHIBIT A";
        const subtitle =
          document.getElementById("sep-subtitle").value || "Forms";

        const preview = document.getElementById("separator-preview");
        preview.innerHTML = `
                <div class="sep-letter">${title}</div>
                <div class="sep-title">${subtitle}</div>
            `;
      }

      function addSeparatorToExhibit() {
        const letter = packageState.currentExhibit;
        const title =
          document.getElementById("sep-title").value || `EXHIBIT ${letter}`;
        const subtitle =
          document.getElementById("sep-subtitle").value ||
          EXHIBITS[letter].name;

        packageState.exhibits[letter].separator = {
          title: title,
          subtitle: subtitle,
        };

        updateExhibitCount(letter);
        renderExhibitDocuments();
        showMessage(
          "package-message",
          "success",
          `Separator added to Exhibit ${letter}`
        );
      }

      // Validate Package before building
      async function validatePackage() {
        const validationResult = document.getElementById("validation-result");
        validationResult.style.display = "block";
        validationResult.innerHTML =
          '<p style="color: var(--text-secondary);">Validating package...</p>';

        try {
          // Build structure data (same logic as buildPackage)
          const structure = [];
          Object.keys(EXHIBITS).forEach((letter) => {
            const exhibit = packageState.exhibits[letter];
            if (exhibit.separator || exhibit.files.length > 0) {
              structure.push({
                letter: letter,
                name: EXHIBITS[letter].name,
                separator: exhibit.separator,
                files: exhibit.files.map((doc, idx) => ({
                  index: idx,
                  name: doc.name,
                })),
              });
            }
          });

          const formData = new FormData();
          formData.append("structure", JSON.stringify(structure));

          const response = await fetch("/api/package/validate", {
            method: "POST",
            body: formData,
          });

          const result = await response.json();

          // Display validation results
          let html = "";

          if (result.valid) {
            html +=
              '<div style="background: rgba(46, 204, 113, 0.1); border-left: 4px solid #2ecc71; padding: 1rem; margin-bottom: 0.5rem; border-radius: 4px;">';
            html += '<strong style="color: #2ecc71;">Package Valid</strong>';
            html +=
              '<p style="margin: 0.5rem 0 0 0; color: var(--text-secondary);">All required exhibits are present.</p>';
            html += "</div>";
          }

          // Issues (critical)
          if (result.issues && result.issues.length > 0) {
            html +=
              '<div style="background: rgba(231, 76, 60, 0.1); border-left: 4px solid #e74c3c; padding: 1rem; margin-bottom: 0.5rem; border-radius: 4px;">';
            html += '<strong style="color: #e74c3c;">Issues Found</strong>';
            html +=
              '<ul style="margin: 0.5rem 0 0 0; color: var(--text-secondary);">';
            result.issues.forEach((issue) => {
              html += `<li>${issue.message}</li>`;
            });
            html += "</ul></div>";
          }

          // Warnings
          if (result.warnings && result.warnings.length > 0) {
            html +=
              '<div style="background: rgba(241, 196, 15, 0.1); border-left: 4px solid #f1c40f; padding: 1rem; margin-bottom: 0.5rem; border-radius: 4px;">';
            html += '<strong style="color: #f1c40f;">Warnings</strong>';
            html +=
              '<ul style="margin: 0.5rem 0 0 0; color: var(--text-secondary);">';
            result.warnings.forEach((warning) => {
              html += `<li>${warning.message}</li>`;
            });
            html += "</ul></div>";
          }

          // Info
          if (result.info && result.info.length > 0) {
            html +=
              '<div style="background: rgba(52, 152, 219, 0.1); border-left: 4px solid #3498db; padding: 1rem; margin-bottom: 0.5rem; border-radius: 4px;">';
            html += '<strong style="color: #3498db;">Suggestions</strong>';
            html +=
              '<ul style="margin: 0.5rem 0 0 0; color: var(--text-secondary);">';
            result.info.forEach((info) => {
              html += `<li>${info.message}</li>`;
            });
            html += "</ul></div>";
          }

          // Summary
          if (result.summary) {
            html +=
              '<div style="background: var(--bg-tertiary); padding: 1rem; border-radius: 4px; margin-top: 0.5rem;">';
            html +=
              '<strong style="color: var(--text-primary);">Summary</strong>';
            html += `<p style="margin: 0.5rem 0 0 0; color: var(--text-secondary);">`;
            html += `Exhibits: ${
              result.summary.exhibits_present.join(", ") || "None"
            } | `;
            html += `Files: ${result.summary.total_files || 0}`;
            html += "</p></div>";
          }

          validationResult.innerHTML = html;
        } catch (error) {
          validationResult.innerHTML = `<div style="background: rgba(231, 76, 60, 0.1); border-left: 4px solid #e74c3c; padding: 1rem; border-radius: 4px;">`;
          validationResult.innerHTML += `<strong style="color: #e74c3c;">Validation Error</strong>`;
          validationResult.innerHTML += `<p style="margin: 0.5rem 0 0 0; color: var(--text-secondary);">${error.message}</p></div>`;
        }
      }

      async function buildPackage() {
        const loading = document.getElementById("package-loading");
        loading.classList.add("active");

        try {
          const formData = new FormData();

          // Collect all files in order
          let fileIndex = 0;
          const structure = [];

          Object.keys(EXHIBITS).forEach((letter) => {
            const exhibit = packageState.exhibits[letter];

            if (exhibit.separator || exhibit.files.length > 0) {
              const exhibitData = {
                letter: letter,
                name: EXHIBITS[letter].name,
                separator: exhibit.separator,
                files: [],
              };

              exhibit.files.forEach((doc) => {
                formData.append("files", doc.file);
                exhibitData.files.push({
                  index: fileIndex,
                  name: doc.name,
                });
                fileIndex++;
              });

              structure.push(exhibitData);
            }
          });

          // Get cover page and options
          const includeCover = document.getElementById("include-cover").checked;
          const beneficiaryName =
            document.getElementById("cover-beneficiary").value;
          const visaType =
            document.getElementById("cover-visa").value || "EB-2 NIW";
          const caseNumber = document.getElementById("cover-case-number").value;
          const includeTOC = document.getElementById("include-toc").checked;
          const addPageNums =
            document.getElementById("add-page-numbers").checked;
          const addWatermark = document.getElementById("add-watermark").checked;

          // Validate: need either files or cover page
          if (
            fileIndex === 0 &&
            structure.every((s) => !s.separator) &&
            !includeCover
          ) {
            showMessage(
              "package-message",
              "error",
              "Please upload at least one document or add a separator"
            );
            loading.classList.remove("active");
            return;
          }

          // Validate: cover page needs beneficiary name
          if (includeCover && !beneficiaryName) {
            showMessage(
              "package-message",
              "error",
              "Please enter beneficiary name for the cover page"
            );
            loading.classList.remove("active");
            return;
          }

          formData.append("structure", JSON.stringify(structure));
          formData.append("include_cover", includeCover);
          formData.append("beneficiary_name", beneficiaryName);
          formData.append("visa_type", visaType);
          formData.append("case_number", caseNumber);
          formData.append("include_toc", includeTOC);
          formData.append("add_page_nums", addPageNums);
          formData.append("add_watermark_text", addWatermark ? "DRAFT" : "");

          const response = await fetch("/api/package/build", {
            method: "POST",
            body: formData,
          });

          const result = await response.json();

          if (result.success) {
            showMessage(
              "package-message",
              "success",
              `Package built: ${result.filename} (${result.page_count} pages, ${result.exhibits_count} exhibits)`,
              result.download_url
            );
          } else {
            showMessage("package-message", "error", `Error: ${result.error}`);
          }
        } catch (error) {
          showMessage("package-message", "error", `Error: ${error.message}`);
        } finally {
          loading.classList.remove("active");
        }
      }

      // ===========================================
      // Exhibit Checklists
      // ===========================================

      const EXHIBIT_CHECKLISTS = {
        A: ["I-140 Form", "ETA-9089", "G-1145", "G-28 (if attorney)"],
        B: ["Cover Letter", "Table of Contents", "Legal Brief"],
        C: [
          "Curriculum Vitae",
          "Personal Statement",
          "Diplomas",
          "Certifications",
          "Passport copy",
        ],
        D: [
          "LOR 1 (Supervisor)",
          "LOR 2 (Colleague)",
          "LOR 3 (Expert)",
          "LOR 4-6 (Additional)",
        ],
        E: ["W-2 Forms", "Pay stubs", "Offer letter", "Salary verification"],
        F: [
          "IEEE membership",
          "Professional associations",
          "Membership certificates",
        ],
        G: [
          "Peer review evidence",
          "Journal reviewer invitations",
          "Committee participation",
        ],
        H: ["Citations list", "Papers citing your work", "Acknowledgments"],
        I: ["Awards certificates", "Recognition letters", "Honor society"],
        J: ["Employment offers", "Job contracts", "Consulting agreements"],
        K: ["Press articles", "News mentions", "Interview transcripts"],
        L: ["Patents", "Publications", "Technical reports"],
        M: [
          "Government documents",
          "Industry statistics",
          "Supporting research",
        ],
      };

      function renderExhibitChecklist(letter) {
        const items = EXHIBIT_CHECKLISTS[letter] || [];
        const uploadedFiles = packageState.exhibits[letter].files.map((f) =>
          f.name.toLowerCase()
        );

        let html = '<ul style="list-style: none; padding: 0; margin: 0;">';
        items.forEach((item) => {
          const itemLower = item.toLowerCase();
          const matched = uploadedFiles.some(
            (f) =>
              f.includes(itemLower.split(" ")[0]) ||
              f.includes(itemLower.split(" ").slice(0, 2).join(""))
          );
          const icon = matched ? "&#x2713;" : "&#x25CB;";
          const color = matched ? "var(--success)" : "var(--text-secondary)";
          html += `<li style="color: ${color}; padding: 0.3rem 0;">${icon} ${item}</li>`;
        });
        html += "</ul>";

        document.getElementById("exhibit-checklist").innerHTML = html;
      }

      // ===========================================
      // Save/Load Draft
      // ===========================================

      function saveDraft() {
        const draft = {
          timestamp: new Date().toISOString(),
          coverPage: {
            beneficiary: document.getElementById("cover-beneficiary").value,
            visaType: document.getElementById("cover-visa").value,
            caseNumber: document.getElementById("cover-case-number").value,
            includeCover: document.getElementById("include-cover").checked,
            includeTOC: document.getElementById("include-toc").checked,
            addPageNumbers: document.getElementById("add-page-numbers").checked,
            addWatermark: document.getElementById("add-watermark").checked,
          },
          exhibits: {},
        };

        // Save exhibit separators (files can't be saved due to browser security)
        Object.keys(EXHIBITS).forEach((letter) => {
          draft.exhibits[letter] = {
            separator: packageState.exhibits[letter].separator,
            fileCount: packageState.exhibits[letter].files.length,
          };
        });

        localStorage.setItem("ilc_package_draft", JSON.stringify(draft));
        showMessage("package-message", "success", "Draft saved successfully!");
      }

      function loadDraft() {
        const saved = localStorage.getItem("ilc_package_draft");
        if (!saved) {
          showMessage("package-message", "error", "No draft found");
          return;
        }

        const draft = JSON.parse(saved);

        // Restore cover page settings
        if (draft.coverPage) {
          document.getElementById("cover-beneficiary").value =
            draft.coverPage.beneficiary || "";
          document.getElementById("cover-visa").value =
            draft.coverPage.visaType || "EB-2 NIW";
          document.getElementById("cover-case-number").value =
            draft.coverPage.caseNumber || "";
          document.getElementById("include-cover").checked =
            draft.coverPage.includeCover !== false;
          document.getElementById("include-toc").checked =
            draft.coverPage.includeTOC !== false;
          document.getElementById("add-page-numbers").checked =
            draft.coverPage.addPageNumbers !== false;
          document.getElementById("add-watermark").checked =
            draft.coverPage.addWatermark || false;
        }

        // Restore separators
        if (draft.exhibits) {
          Object.keys(draft.exhibits).forEach((letter) => {
            if (draft.exhibits[letter].separator) {
              packageState.exhibits[letter].separator =
                draft.exhibits[letter].separator;
              updateExhibitCount(letter);
            }
          });
        }

        renderExhibitDocuments();
        showMessage(
          "package-message",
          "success",
          `Draft loaded from ${new Date(
            draft.timestamp
          ).toLocaleString()}. Note: Files must be re-uploaded.`
        );
      }

      // ===========================================
      // Debug Panel
      // ===========================================

      async function refreshDebugLog() {
        try {
          const response = await fetch("/api/debug/logs?lines=50");
          const data = await response.json();
          const logPre = document.getElementById("debug-log");
          logPre.textContent = data.logs.join("");
        } catch (error) {
          document.getElementById("debug-log").textContent =
            "Error loading logs: " + error.message;
        }
      }

      // Toggle debug panel with Ctrl+Shift+D
      document.addEventListener("keydown", function (e) {
        if (e.ctrlKey && e.shiftKey && e.key === "D") {
          const panel = document.getElementById("debug-panel");
          if (panel.style.display === "none") {
            panel.style.display = "block";
            refreshDebugLog();
          } else {
            panel.style.display = "none";
          }
        }
      });

      // PDF.js Preview
      let pdfDoc = null;
      let pageNum = 1;
      let pageRendering = false;

      async function previewPackage() {
        // Build the package first, then preview
        showMessage("package-message", "info", "Building preview...");

        const formData = new FormData();

        // Gather all files from exhibits
        let hasFiles = false;
        for (const [letter, exhibit] of Object.entries(packageState.exhibits)) {
          if (exhibit.files && exhibit.files.length > 0) {
            hasFiles = true;
            for (const file of exhibit.files) {
              formData.append("files", file);
            }
          }
        }

        if (!hasFiles) {
          showMessage(
            "package-message",
            "error",
            "No files to preview. Upload files to exhibits first."
          );
          return;
        }

        formData.append(
          "structure",
          JSON.stringify(
            Object.entries(packageState.exhibits)
              .filter(([_, e]) => e.files.length > 0)
              .map(([letter, e]) => ({
                letter: letter,
                name: e.name,
                files: e.files.map((f) => f.name),
              }))
          )
        );

        try {
          const response = await fetch("/api/package/build", {
            method: "POST",
            body: formData,
          });

          if (!response.ok) throw new Error("Build failed");

          const blob = await response.blob();
          await loadPdfPreview(blob);
          showMessage("package-message", "success", "Preview loaded!");
        } catch (error) {
          showMessage(
            "package-message",
            "error",
            "Preview failed: " + error.message
          );
        }
      }

      async function loadPdfPreview(source) {
        // source can be: Blob, File, ArrayBuffer, or URL string
        let loadingTask;

        if (source instanceof Blob || source instanceof File) {
          const arrayBuffer = await source.arrayBuffer();
          loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
        } else if (typeof source === "string") {
          loadingTask = pdfjsLib.getDocument(source);
        } else {
          loadingTask = pdfjsLib.getDocument({ data: source });
        }

        pdfDoc = await loadingTask.promise;
        pageNum = 1;

        document.getElementById("preview-container").style.display = "block";
        await renderPage(pageNum);
      }

      async function previewUploadedFile(file) {
        if (file.type === "application/pdf") {
          await loadPdfPreview(file);
        } else if (file.type.startsWith("image/")) {
          // Show image preview
          const url = URL.createObjectURL(file);
          const container = document.getElementById("pdf-canvas-container");
          container.innerHTML = `<img src="${url}" style="max-width: 100%; max-height: 600px;">`;
          document.getElementById("preview-container").style.display = "block";
          document.getElementById("page-info").textContent = "Image Preview";
        } else {
          showMessage(
            "package-message",
            "info",
            "Preview not available for this file type."
          );
        }
      }

      function prevPage() {
        if (pageNum <= 1) return;
        pageNum--;
        renderPage(pageNum);
      }

      function nextPage() {
        if (pageNum >= pdfDoc.numPages) return;
        pageNum++;
        renderPage(pageNum);
      }

      function closePreview() {
        document.getElementById("preview-container").style.display = "none";
      }

      async function renderPage(num) {
        pageRendering = true;
        const page = await pdfDoc.getPage(num);

        const scale = 1.5;
        const viewport = page.getViewport({ scale: scale });

        const canvas = document.getElementById("pdf-canvas");
        const ctx = canvas.getContext("2d");
        canvas.height = viewport.height;
        canvas.width = viewport.width;

        const renderContext = {
          canvasContext: ctx,
          viewport: viewport,
        };

        await page.render(renderContext).promise;
        pageRendering = false;

        document.getElementById(
          "page-info"
        ).textContent = `Page ${num} of ${pdfDoc.numPages}`;
      }

      // PDF Tools Preview (separate state from Package preview)
      let pdfToolsDoc = null;
      let pdfToolsPageNum = 1;

      async function loadPdfToolsPreview(source) {
        let loadingTask;

        if (source instanceof Blob || source instanceof File) {
          const arrayBuffer = await source.arrayBuffer();
          loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
        } else if (typeof source === "string") {
          loadingTask = pdfjsLib.getDocument(source);
        } else {
          loadingTask = pdfjsLib.getDocument({ data: source });
        }

        pdfToolsDoc = await loadingTask.promise;
        pdfToolsPageNum = 1;

        document.getElementById("pdf-tools-preview").style.display = "block";
        await renderPageTools(pdfToolsPageNum);
      }

      async function renderPageTools(num) {
        const page = await pdfToolsDoc.getPage(num);
        const scale = 1.2;
        const viewport = page.getViewport({ scale: scale });

        const canvas = document.getElementById("pdf-tools-canvas");
        const ctx = canvas.getContext("2d");
        canvas.height = viewport.height;
        canvas.width = viewport.width;

        await page.render({
          canvasContext: ctx,
          viewport: viewport,
        }).promise;

        document.getElementById(
          "pdf-tools-page-info"
        ).textContent = `Page ${num} of ${pdfToolsDoc.numPages}`;
      }

      function prevPageTools() {
        if (pdfToolsPageNum <= 1) return;
        pdfToolsPageNum--;
        renderPageTools(pdfToolsPageNum);
      }

      function nextPageTools() {
        if (pdfToolsPageNum >= pdfToolsDoc.numPages) return;
        pdfToolsPageNum++;
        renderPageTools(pdfToolsPageNum);
      }

      function closePdfToolsPreview() {
        document.getElementById("pdf-tools-preview").style.display = "none";
        pdfToolsDoc = null;
      }

      // Preview result after merge/convert
      async function previewPdfResult(blob) {
        try {
          await loadPdfToolsPreview(blob);
        } catch (error) {
          console.error("Preview error:", error);
        }
      }

      // ===========================================
      // Google Drive Import
      // ===========================================

      let currentDriveTarget = null; // 'merge', 'images', 'package', etc.

      async function importFromDrive(target) {
        currentDriveTarget = target;

        // Check if Google API credentials are configured (empty when env vars unset)
        if (!GOOGLE_API_KEY || GOOGLE_API_KEY === "YOUR_API_KEY") {
          showGoogleSetupModal();
          return;
        }

        // Initialize token client if needed
        if (!googleAccessToken) {
          const tokenClient = google.accounts.oauth2.initTokenClient({
            client_id: GOOGLE_CLIENT_ID,
            scope: SCOPES,
            callback: (response) => {
              if (response.access_token) {
                googleAccessToken = response.access_token;
                createPicker();
              }
            },
          });
          tokenClient.requestAccessToken({ prompt: "consent" });
        } else {
          createPicker();
        }
      }

      function createPicker() {
        const docsView = new google.picker.DocsView()
          .setIncludeFolders(true)
          .setSelectFolderEnabled(false);

        // Set mime types based on target
        if (currentDriveTarget === "images") {
          docsView.setMimeTypes("image/jpeg,image/png,image/gif,image/webp");
        } else {
          docsView.setMimeTypes(
            "application/pdf,application/vnd.google-apps.document,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,image/jpeg,image/png"
          );
        }

        const picker = new google.picker.PickerBuilder()
          .addView(docsView)
          .setOAuthToken(googleAccessToken)
          .setDeveloperKey(GOOGLE_API_KEY)
          .setAppId(GOOGLE_APP_ID)
          .setCallback(pickerCallback)
          .enableFeature(google.picker.Feature.MULTISELECT_ENABLED)
          .setTitle("Select files from Google Drive")
          .build();

        picker.setVisible(true);
      }

      async function pickerCallback(data) {
        if (data.action === google.picker.Action.PICKED) {
          const files = data.docs;
          showMessage(
            "pdf-message",
            "info",
            `Importing ${files.length} file(s) from Google Drive...`
          );

          for (const file of files) {
            try {
              await downloadAndAddFile(file);
            } catch (error) {
              console.error("Error importing file:", file.name, error);
            }
          }

          showMessage(
            "pdf-message",
            "success",
            `Imported ${files.length} file(s) from Google Drive!`
          );
        }
      }

      async function downloadAndAddFile(driveFile) {
        let downloadUrl;
        let filename = driveFile.name;

        // Handle Google Docs - export as PDF
        if (driveFile.mimeType === "application/vnd.google-apps.document") {
          downloadUrl = `https://www.googleapis.com/drive/v3/files/${driveFile.id}/export?mimeType=application/pdf`;
          filename = driveFile.name + ".pdf";
        } else if (
          driveFile.mimeType === "application/vnd.google-apps.spreadsheet"
        ) {
          downloadUrl = `https://www.googleapis.com/drive/v3/files/${driveFile.id}/export?mimeType=application/pdf`;
          filename = driveFile.name + ".pdf";
        } else {
          // Regular file - download directly
          downloadUrl = `https://www.googleapis.com/drive/v3/files/${driveFile.id}?alt=media`;
        }

        const response = await fetch(downloadUrl, {
          headers: {
            Authorization: `Bearer ${googleAccessToken}`,
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to download: ${response.statusText}`);
        }

        const blob = await response.blob();
        const file = new File([blob], filename, {
          type: blob.type || "application/octet-stream",
        });

        // Add to appropriate target
        addFileToTarget(file, currentDriveTarget);
      }

      function addFileToTarget(file, target) {
        let inputElement;
        let listElement;

        switch (target) {
          case "merge":
            inputElement = document.getElementById("merge-files");
            listElement = "merge-list";
            break;
          case "images":
            inputElement = document.getElementById("image-files");
            listElement = "images-list";
            break;
          default:
            console.warn("Unknown target:", target);
            return;
        }

        // Create a DataTransfer to simulate file input
        const dt = new DataTransfer();

        // Add existing files
        if (inputElement.files) {
          for (const f of inputElement.files) {
            dt.items.add(f);
          }
        }

        // Add new file
        dt.items.add(file);

        // Update input
        inputElement.files = dt.files;

        // Update file list display
        updateFileList(inputElement, listElement);
      }

      function showGoogleSetupModal() {
        const modal = document.createElement("div");
        modal.style.cssText =
          "position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center; z-index: 10000;";
        modal.innerHTML = `
                <div style="background: var(--bg-secondary); padding: 2rem; border-radius: 8px; max-width: 600px; color: var(--text-primary);">
                    <h2 style="margin-top: 0;">Google Drive Setup Required</h2>
                    <p>To use Google Drive import, you need to configure Google Cloud credentials:</p>
                    <ol style="color: var(--text-secondary); line-height: 1.8;">
                        <li>Go to <a href="https://console.cloud.google.com" target="_blank" style="color: var(--accent);">Google Cloud Console</a></li>
                        <li>Create a new project (or use existing)</li>
                        <li>Enable <strong>Google Drive API</strong> and <strong>Google Picker API</strong></li>
                        <li>Create OAuth 2.0 credentials (Web application)</li>
                        <li>Add your domain to authorized JavaScript origins</li>
                        <li>Create an API Key</li>
                        <li>Update the credentials in the code or contact the administrator</li>
                    </ol>
                    <button onclick="this.parentElement.parentElement.remove()" class="btn" style="margin-top: 1rem;">Close</button>
                </div>
            `;
        document.body.appendChild(modal);
      }

        // ===========================================
        // PS Extract Tool
        // ===========================================

        let extractPendingFile = null;

        async function importForPSExtract(source) {
            if (source === 'gdrive') {
                currentDriveTarget = 'ps-extract';
                // Re-use existing auth logic (empty when env vars unset)
                if (!GOOGLE_API_KEY || GOOGLE_API_KEY === 'YOUR_API_KEY') {
                    showGoogleSetupModal();
                    return;
                }
                if (!googleAccessToken) {
                    const tokenClient = google.accounts.oauth2.initTokenClient({
                        client_id: GOOGLE_CLIENT_ID,
                        scope: SCOPES,
                        callback: (response) => {
                            if (response.access_token) {
                                googleAccessToken = response.access_token;
                                createPicker();
                            }
                        }
                    });
                    tokenClient.requestAccessToken({ prompt: 'consent' });
                } else {
                    createPicker();
                }
            }
        }

        // Handle file selected from Drive for Extract
        // (Called from addFileToTarget when target is 'ps-extract')
        // We need to modify addFileToTarget to handle this case
        
        function handlePSExtractFile(input) {
            if (input.files.length > 0) {
                extractPendingFile = input.files[0];
                processExtraction();
            }
        }

        async function processExtraction() {
            if (!extractPendingFile) return;

            const statusDiv = document.getElementById('ps-extract-status');
            const statusText = document.getElementById('ps-extract-status-text');
            statusDiv.style.display = 'flex';
            statusText.textContent = 'Analyzing document...';

            const formData = new FormData();
            formData.append('file', extractPendingFile);
            formData.append('context', document.getElementById('ps-extract-context').value);
            formData.append('fix_errors', document.getElementById('ps-fix-errors').checked);
            formData.append('complete_sections', document.getElementById('ps-complete-sections').checked);
            formData.append('enhance_language', document.getElementById('ps-enhance-language').checked);

            try {
                const response = await fetch('/api/ps/extract', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    fillPSForm(data.extracted);
                    showMessage('ps-message', 'success', 'Document analyzed! Fields have been filled. Review and edit as needed.');
                    
                    // Trigger quality check
                    setTimeout(analyzeFormForChecklist, 500);
                } else {
                    showMessage('ps-message', 'error', data.error || 'Extraction failed');
                }
            } catch (error) {
                showMessage('ps-message', 'error', 'Error processing document: ' + error.message);
            } finally {
                statusDiv.style.display = 'none';
                extractPendingFile = null;
                // clear file input
                document.getElementById('ps-extract-file').value = '';
            }
        }

        function fillPSForm(extracted) {
            // Helper to set value if exists
            const setVal = (selector, val) => {
                const el = document.querySelector(selector);
                if (el && val) el.value = val;
            };
            
            // Helper to set select if value matches roughly
            const setSelect = (selector, val) => {
                const el = document.querySelector(selector);
                if (el && val) {
                   // Try exact match
                   el.value = val;
                   // If not, try to find close match or add new
                   if (el.value !== val) {
                       // Check options
                       for (let opt of el.options) {
                           if (opt.value.includes(val) || val.includes(opt.value)) {
                               el.value = opt.value;
                               return;
                           }
                       }
                       // If customizable, add it
                       if (el.id === 'ps_field') {
                           addOptionToAllSelects('field', val.toLowerCase().replace(/[^a-z0-9]/g, '_'), val);
                           el.value = val.toLowerCase().replace(/[^a-z0-9]/g, '_');
                       }
                   }
                }
            };

            setVal('input[name="beneficiary_name"]', extracted.beneficiary_name);
            setSelect('#ps_field', extracted.field);
            
            setVal('textarea[name="overview"]', extracted.overview);
            setVal('textarea[name="national_importance"]', extracted.national_importance);
            setVal('textarea[name="practical_impact"]', extracted.practical_impact);
            setVal('textarea[name="well_positioned"]', extracted.well_positioned);
            setVal('textarea[name="conclusion"]', extracted.conclusion);

            if (extracted.suggestions && extracted.suggestions.length > 0) {
                showSuggestionsPanel(extracted.suggestions);
            }
        }

        function showSuggestionsPanel(suggestions) {
            const panel = document.getElementById('ps-suggestions-panel');
            const list = document.getElementById('ps-suggestions-list');
            list.innerHTML = '';
            
            suggestions.forEach(s => {
                const li = document.createElement('li');
                li.textContent = s;
                li.style.marginBottom = '0.5rem';
                list.appendChild(li);
            });
            
            panel.style.display = 'block';
        }

        // ===========================================
        // PS Quality Checklist
        // ===========================================

        function analyzeFormForChecklist() {
            const overview = document.querySelector('textarea[name="overview"]')?.value || "";
            const national = document.querySelector('textarea[name="national_importance"]')?.value || "";
            const practical = document.querySelector('textarea[name="practical_impact"]')?.value || ""; // Note: practical might be merged in some templates, but let's assume standard
            const positioned = document.querySelector('textarea[name="well_positioned"]')?.value || "";
            const conclusion = document.querySelector('textarea[name="conclusion"]')?.value || "";
            
            // If practical_impact textarea doesn't exist (depending on template version), use empty
            
            const allText = (overview + " " + national + " " + (practical||"") + " " + positioned + " " + conclusion).toLowerCase();
            const textRaw = overview + national + (practical||"") + positioned + conclusion;

            // Helper to check regex
            const check = (id, regex) => {
                const el = document.getElementById(id);
                if (el) el.checked = regex.test(allText) || regex.test(textRaw);
            };
            
            // Helper for length
            const checkLen = (id, text, minLen) => {
                const el = document.getElementById(id);
                if (el) el.checked = text.length > minLen;
            };

            // Prong 1
            checkLen('ck-endeavor-defined', overview, 200);
            checkLen('ck-field-importance', national, 200);
            check('ck-gov-priorities', /executive order|act of|legislation|federal priority|white house|ostp|critical|strategic/i);
            check('ck-statistics', /\d+%|\d+ (million|billion|thousand)|according to|report|study|census|bureau/i);
            check('ck-broader-impact', /national|united states|american|country|society|globally|economy|healthcare|security/i);

            // Prong 2
            check('ck-education', /degree|university|ph\.?d|master|bachelor|graduate|academic/i);
            check('ck-experience', /years? (of )?experience|worked at|position|role|career|history/i);
            check('ck-achievements', /achieved|accomplished|developed|created|led|managed|designed|invented|published/i);
            check('ck-skills', /expertise|specialized|proficient|skilled|knowledge|technical|competence/i);
            check('ck-track-record', /track record|history of|demonstrated|proven|success|award|recognition/i);
            check('ck-future-plans', /plan to|will continue|intend to|propose to|goal is|aim to/i);

            // Prong 3
            check('ck-labor-cert', /labor certification|perm|traditional process|job offer|specific employer/i);
            check('ck-urgency', /urgency|critical|immediate|time-sensitive|current need|pressing/i);
            check('ck-us-benefit', /benefit.*united states|national interest|public good|welfare/i);
            check('ck-detriment', /loss|detriment|without|deny|denied|deprive/i);

            // Format
            check('ck-first-person', /\b(i|my|me)\b/i);
            // Professional: check for lack of slang (inverse logic not easily doable with simple regex check=true, but we can check existence of good words)
            check('ck-professional', /sincerely|respectfully|submitted|petition|adjudication/i); 
            check('ck-specific', /\d{4}|specific|particular|example|instance|case/i);
            const totalLen = allText.length;
            const elLen = document.getElementById('ck-length');
            if (elLen) elLen.checked = totalLen > 3000; // rough approx for 5 pages

            updateChecklistProgress();
        }

        function updateChecklistProgress() {
            const checkboxes = document.querySelectorAll('.checklist-item input[type="checkbox"]');
            const checked = Array.from(checkboxes).filter(cb => cb.checked).length;
            const total = checkboxes.length;

            const progressEl = document.getElementById('ps-checklist-progress');
            const barEl = document.getElementById('ps-checklist-bar');
            
            if (progressEl) progressEl.textContent = `${checked} / ${total} items`;
            if (barEl) {
                const pct = (checked/total)*100;
                barEl.style.width = `${pct}%`;
                
                if (pct < 30) barEl.style.background = '#e74c3c';
                else if (pct < 80) barEl.style.background = '#f39c12';
                else barEl.style.background = '#2ecc71';
            }
        }

        // Attach listeners to textareas
        document.addEventListener('DOMContentLoaded', () => {
            document.querySelectorAll('#ps-form textarea').forEach(textarea => {
                textarea.addEventListener('input', () => {
                    // Debounce
                    clearTimeout(window.psAnalyzeTimeout);
                    window.psAnalyzeTimeout = setTimeout(analyzeFormForChecklist, 1000);
                });
            });
        });

        // ===========================================
        // Package Checklist
        // ===========================================

        function loadChecklistTemplate() {
            const type = document.getElementById('checklist-visa-type').value;
            // Logic to show/hide items based on type
            // For now, EB-1A items are hidden by default via CSS class .eb1a-only
            // We can toggle them
            
            const eb1aItems = document.querySelectorAll('.eb1a-only');
            const eb1aExhibits = document.querySelector('.eb1a-exhibits');
            
            if (type === 'eb1a' || type === 'custom') {
                eb1aItems.forEach(el => el.style.display = 'flex');
                if (eb1aExhibits) eb1aExhibits.style.display = 'block';
            } else {
                eb1aItems.forEach(el => el.style.display = 'none');
                if (eb1aExhibits) eb1aExhibits.style.display = 'none';
            }

            // Load saved state for this case/type if available
            loadPackageChecklistState();
        }

        function switchChecklistTab(tab) {
            document.querySelectorAll('.checklist-tab').forEach(t => t.classList.remove('active'));
            document.getElementById('tab-' + tab).classList.add('active');
            
            if (tab === 'mailing') {
                document.getElementById('checklist-mailing').style.display = 'block';
                document.getElementById('checklist-online').style.display = 'none';
            } else {
                document.getElementById('checklist-mailing').style.display = 'none';
                document.getElementById('checklist-online').style.display = 'block';
            }
        }

        function addCustomChecklistItem() {
            const exhibit = document.getElementById('custom-item-exhibit').value;
            const text = document.getElementById('custom-item-text').value;
            
            if (!text) return;
            
            const container = document.getElementById('checklist-' + exhibit);
            if (container) {
                const label = document.createElement('label');
                label.className = 'checklist-item';
                label.innerHTML = `<input type="checkbox"><span>${text}</span>`;
                container.appendChild(label);
                
                // Save custom item to storage
                saveCustomChecklistItem(exhibit, text);
                
                document.getElementById('custom-item-text').value = '';
            }
        }

        function saveCustomChecklistItem(exhibit, text) {
            const customItems = JSON.parse(localStorage.getItem('ilc_custom_checklist_items') || '[]');
            customItems.push({ exhibit, text });
            localStorage.setItem('ilc_custom_checklist_items', JSON.stringify(customItems));
        }

        function loadPackageChecklistState() {
            // Load custom items
            const customItems = JSON.parse(localStorage.getItem('ilc_custom_checklist_items') || '[]');
            customItems.forEach(item => {
                const container = document.getElementById('checklist-' + item.exhibit);
                // Check if already exists to avoid dupes
                const exists = Array.from(container.querySelectorAll('span')).some(s => s.textContent === item.text);
                if (container && !exists) {
                    const label = document.createElement('label');
                    label.className = 'checklist-item';
                    label.innerHTML = `<input type="checkbox"><span>${item.text}</span>`;
                    container.appendChild(label);
                }
            });
            
            // Load checked state
             const checkedState = JSON.parse(localStorage.getItem('ilc_package_checklist_state') || '{}');
             document.querySelectorAll('#checklist-mailing input[type="checkbox"]').forEach((cb, idx) => {
                 // Simple index-based state for now, ideally use IDs
                 if (checkedState[idx]) cb.checked = true;
                 
                 cb.addEventListener('change', () => {
                     savePackageChecklistState();
                     updatePackageChecklistProgress();
                 });
             });
             
             updatePackageChecklistProgress();
        }

        function savePackageChecklistState() {
            const state = {};
            document.querySelectorAll('#checklist-mailing input[type="checkbox"]').forEach((cb, idx) => {
                if (cb.checked) state[idx] = true;
            });
            localStorage.setItem('ilc_package_checklist_state', JSON.stringify(state));
        }
        
        function saveCustomChecklist() {
            // Saves the current configuration as a preset (UI stub for now)
            alert('Custom checklist configuration saved!');
        }

        function updatePackageChecklistProgress() {
            const checkboxes = document.querySelectorAll('#checklist-mailing input[type="checkbox"]');
            const checked = Array.from(checkboxes).filter(cb => cb.checked).length;
            const total = checkboxes.length;
            
            const progressEl = document.getElementById('package-checklist-progress');
            const barEl = document.getElementById('package-checklist-bar');
            
            if (progressEl) progressEl.textContent = `${checked} / ${total} items`;
            if (barEl) {
                const pct = total > 0 ? (checked/total)*100 : 0;
                barEl.style.width = `${pct}%`;
            }
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
             // Handle hash navigation
             const hash = window.location.hash.substring(1); // e.g. "package-section"
             if (hash) {
                 const section = hash.replace('-section', '');
                 if (['lor', 'ps', 'package', 'pdf', 'clients'].includes(section)) {
                     showSection(section);
                 }
             }

             loadChecklistTemplate();
             // Hook into existing addFileToTarget to handle ps-extract
             const originalAddFile = window.addFileToTarget;
             // We can't easily overwrite, so we modify the logic in our new functions above
             // or redefine it if we want.
             // Redefining addFileToTarget:
             window.addFileToTarget = function(file, target) {
                 if (target === 'ps-extract') {
                     extractPendingFile = file;
                     processExtraction();
                     return;
                 }
                 
                 // Original logic copy
                 let inputElement;
                 let listElement;

                 switch (target) {
                     case 'merge':
                         inputElement = document.getElementById('merge-files');
                         listElement = 'merge-list';
                         break;
                     case 'images':
                         inputElement = document.getElementById('image-files');
                         listElement = 'images-list';
                         break;
                     // Add package target if needed
                     default:
                         // Fallback for check
                         console.warn('Unknown target:', target);
                         return;
                 }
                 
                 const dt = new DataTransfer();
                 if (inputElement.files) {
                    for (const f of inputElement.files) dt.items.add(f);
                 }
                 dt.items.add(file);
                 inputElement.files = dt.files;
                 updateFileList(inputElement, listElement);
             };
        });

// Cookie helper functions
        function setCookie(name, value, days = 1) {
            const expires = new Date(Date.now() + days * 24 * 60 * 60 * 1000).toUTCString();
            // SameSite=Lax allows cookies on navigation (F5, links)
            document.cookie = `${name}=${value}; expires=${expires}; path=/; SameSite=Lax; Secure`;
        }

        function getCookie(name) {
            const value = `; ${document.cookie}`;
            const parts = value.split(`; ${name}=`);
            if (parts.length === 2) return parts.pop().split(';').shift();
            return null;
        }

        function deleteCookie(name) {
            document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
        }

        function clearAllTokens() {
            localStorage.removeItem('ilc_access_token');
            localStorage.removeItem('ilc_refresh_token');
            deleteCookie('ilc_access_token');
            deleteCookie('ilc_refresh_token');
        }

        // Sync localStorage to cookies (ensures cookies exist even if lost)
        function syncTokensToCookies() {
            const accessToken = localStorage.getItem('ilc_access_token');
            const refreshToken = localStorage.getItem('ilc_refresh_token');
            if (accessToken && !getCookie('ilc_access_token')) {
                setCookie('ilc_access_token', accessToken, 1/24);
            }
            if (refreshToken && !getCookie('ilc_refresh_token')) {
                setCookie('ilc_refresh_token', refreshToken, 7);
            }
        }

        // NOTE: Server-side auth now protects this page
        // This script provides token refresh and logout functionality
        (function() {
            // First, ensure cookies are synced from localStorage
            syncTokensToCookies();

            const token = localStorage.getItem('ilc_access_token');

            // Update UI with user info if token exists
            if (token) {
                fetch('/api/auth/me', {
                    headers: { 'Authorization': `Bearer ${token}` }
                }).then(response => {
                    if (response.ok) {
                        return response.json();
                    }
                    // Token invalid (401/403), try to refresh
                    if (response.status === 401 || response.status === 403) {
                        const refreshToken = localStorage.getItem('ilc_refresh_token');
                        if (refreshToken) {
                            return fetch('/api/auth/refresh', {
                                method: 'POST',
                                headers: { 'Authorization': `Bearer ${refreshToken}` }
                            }).then(refreshResponse => {
                                if (refreshResponse.ok) {
                                    return refreshResponse.json().then(data => {
                                        localStorage.setItem('ilc_access_token', data.access_token);
                                        setCookie('ilc_access_token', data.access_token, 1/24);
                                        return fetch('/api/auth/me', {
                                            headers: { 'Authorization': `Bearer ${data.access_token}` }
                                        }).then(r => r.json());
                                    });
                                }
                                // Refresh also failed - need to re-login
                                clearAllTokens();
                                throw new Error('Refresh failed');
                            });
                        }
                        // No refresh token - need to re-login
                        clearAllTokens();
                        throw new Error('No refresh token');
                    }
                    // Other error (network, etc) - don't clear tokens
                    throw new Error('Network error');
                }).then(user => {
                    if (user && user.email) {
                        const userDisplay = document.getElementById('user-display');
                        if (userDisplay) {
                            userDisplay.textContent = user.full_name || user.username;
                        }
                    }
                }).catch(err => {
                    // Only log error, don't clear tokens unless it was explicit auth failure
                    // (tokens are already cleared in the specific 401/403 cases above)
                    console.log('Auth check:', err.message);
                });
            }

            // Logout handler - clears all tokens and cookies
            window.logout = function() {
                const token = localStorage.getItem('ilc_access_token');
                fetch('/api/auth/logout', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                }).finally(() => {
                    clearAllTokens();
                    window.location.href = '/tools/login';
                });
            };

            // Add authorization header to all API calls
            const originalFetch = window.fetch;
            window.fetch = function(url, options = {}) {
                if (typeof url === 'string' && url.startsWith('/api/') && !url.includes('/auth/')) {
                    const token = localStorage.getItem('ilc_access_token');
                    if (token) {
                        options.headers = options.headers || {};
                        if (options.headers instanceof Headers) {
                            options.headers.set('Authorization', `Bearer ${token}`);
                        } else {
                            options.headers['Authorization'] = `Bearer ${token}`;
                        }
                    }
                }
                return originalFetch(url, options);
            };
        })();

        // ===========================================
        // Feedback System
        // ===========================================

        function openFeedbackModal() {
            document.getElementById('feedback-modal').classList.add('active');
            document.getElementById('feedback-text').focus();
        }

        function closeFeedbackModal() {
            document.getElementById('feedback-modal').classList.remove('active');
            document.getElementById('feedback-text').value = '';
        }

        async function submitFeedback() {
            const message = document.getElementById('feedback-text').value.trim();
            if (!message) {
                alert('Por favor, escreva uma mensagem.');
                return;
            }

            const submitBtn = document.querySelector('.feedback-modal .btn-submit');
            const originalText = submitBtn.textContent;
            submitBtn.textContent = 'Enviando...';
            submitBtn.disabled = true;

            try {
                const userEmail = localStorage.getItem('ilc_user_email') || '';
                const response = await fetch('api/feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: message,
                        page: window.location.pathname,
                        user_email: userEmail
                    })
                });

                const data = await response.json();
                if (data.success) {
                    alert('Feedback enviado com sucesso! Obrigado.');
                    closeFeedbackModal();
                } else {
                    alert('Erro ao enviar feedback: ' + (data.message || 'Tente novamente.'));
                }
            } catch (error) {
                console.error('Feedback error:', error);
                alert('Erro ao enviar feedback. Tente novamente.');
            } finally {
                submitBtn.textContent = originalText;
                submitBtn.disabled = false;
            }
        }

        // Close modal on escape key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                closeFeedbackModal();
            }
        });

        // Close modal on backdrop click
        document.getElementById('feedback-modal').addEventListener('click', function(e) {
            if (e.target === this) {
                closeFeedbackModal();
            }
        });

        // ===========================================
        // Tasks System (Notion Integration)
        // ===========================================

        let tasksAssignees = [];

        // Load assignees for dropdowns
        async function loadAssignees() {
            try {
                const response = await fetch('/api/tasks/assignees');
                if (response.ok) {
                    const data = await response.json();
                    tasksAssignees = data.assignees || [];
                }
            } catch (error) {
                console.error('Failed to load assignees:', error);
            }
        }

        // =====================================================
        // NOTION-STYLE EDITABLE TABLE
        // =====================================================

        let tasksData = [];
        let notionSchema = null;
        let currentEditingCell = null;

        // Color mappings for status/priority badges
        const statusColors = {
            'A fazer': { bg: '#2d2d2d', text: '#9b9b9b' },
            'To Do': { bg: '#2d2d2d', text: '#9b9b9b' },
            'Em andamento': { bg: '#3d3a50', text: '#a78bfa' },
            'In Progress': { bg: '#3d3a50', text: '#a78bfa' },
            'Doing': { bg: '#3d3a50', text: '#a78bfa' },
            'Concluido': { bg: '#1e3a2f', text: '#4ade80' },
            'Done': { bg: '#1e3a2f', text: '#4ade80' },
            'Cancelado': { bg: '#3d2d2d', text: '#f87171' }
        };

        const priorityColors = {
            'Urgente': { bg: '#4a1d1d', text: '#f87171' },
            'Alta': { bg: '#4a3d1d', text: '#fbbf24' },
            'Media': { bg: '#1d3a4a', text: '#60a5fa' },
            'Baixa': { bg: '#2d2d2d', text: '#9b9b9b' }
        };

        // Load Notion schema (select options, relation items)
        async function loadNotionSchema() {
            try {
                const token = localStorage.getItem('ilc_access_token');
                const response = await fetch('api/notion/schema', {
                    headers: token ? { 'Authorization': `Bearer ${token}` } : {}
                });
                if (response.ok) {
                    notionSchema = await response.json();
                    console.log('Schema loaded:', notionSchema);
                }
            } catch (error) {
                console.error('Failed to load schema:', error);
            }
        }

        // Load tasks from API
        async function loadTasks() {
            const loadingEl = document.getElementById('tasks-loading');
            const tableEl = document.getElementById('notion-table');
            const emptyEl = document.getElementById('tasks-empty');

            if (!loadingEl || !tableEl || !emptyEl) return;

            loadingEl.style.display = 'block';
            tableEl.style.display = 'none';
            emptyEl.style.display = 'none';

            try {
                const token = localStorage.getItem('ilc_access_token');
                const response = await fetch('api/tasks', {
                    headers: token ? { 'Authorization': `Bearer ${token}` } : {}
                });

                if (response.ok) {
                    const data = await response.json();
                    tasksData = data.tasks || [];
                    renderTasksTable();
                    if (currentViewMode === 'kanban') renderKanbanBoard();
                } else if (response.status === 503) {
                    loadingEl.innerHTML = '<p style="color: var(--text-secondary);">Notion integration não configurada.</p>';
                } else if (response.status === 401) {
                    loadingEl.innerHTML = '<p style="color: var(--text-secondary);">Sessão expirada. Faça login novamente.</p>';
                } else {
                    throw new Error('Failed to load tasks');
                }
            } catch (error) {
                console.error('Tasks error:', error);
                loadingEl.innerHTML = '<p style="color: var(--error);">Erro ao carregar tarefas.</p>';
            }
        }

        // Render tasks table
        function renderTasksTable() {
            const loadingEl = document.getElementById('tasks-loading');
            const tableEl = document.getElementById('notion-table');
            const emptyEl = document.getElementById('tasks-empty');
            const tbody = document.getElementById('tasks-tbody');

            loadingEl.style.display = 'none';

            if (tasksData.length === 0) {
                emptyEl.style.display = 'block';
                tableEl.style.display = 'none';
                return;
            }

            tableEl.style.display = 'table';
            tbody.innerHTML = tasksData.map((task, index) => renderTaskRow(task, index)).join('');
        }

        // Render single task row
        function renderTaskRow(task, index) {
            const responsavelNames = getMultiRelationNames('Responsável', task.responsavel?.ids);
            const casoName = getRelationName('Caso', task.caso?.ids);
            const clienteName = getRelationName('Cliente', task.cliente?.ids);

            const statusStyle = statusColors[task.status] || { bg: '#2d2d2d', text: '#9b9b9b' };
            const prioStyle = priorityColors[task.prioridade] || { bg: '#2d2d2d', text: '#9b9b9b' };

            return `
                <tr data-task-id="${task.id}" data-index="${index}">
                    <td onclick="editCell(this, 'tarefa', 'text')" data-prop="tarefa" data-value="${escapeHtml(task.tarefa || '')}">
                        <div class="cell-content">${task.tarefa || '<span class="empty-cell">Sem titulo</span>'}</div>
                    </td>
                    <td onclick="editCell(this, 'responsavel', 'people')" data-prop="responsavel" data-ids="${(task.responsavel?.ids || []).join(',')}">
                        <div class="cell-content">${responsavelNames || '<span class="empty-cell">-</span>'}</div>
                    </td>
                    <td onclick="editCell(this, 'caso', 'relation')" data-prop="caso" data-ids="${(task.caso?.ids || []).join(',')}">
                        <div class="cell-content">${casoName || '<span class="empty-cell">-</span>'}</div>
                    </td>
                    <td onclick="editCell(this, 'cliente', 'relation')" data-prop="cliente" data-ids="${(task.cliente?.ids || []).join(',')}">
                        <div class="cell-content">${clienteName || '<span class="empty-cell">-</span>'}</div>
                    </td>
                    <td onclick="editCell(this, 'status', 'select')" data-prop="status" data-value="${escapeHtml(task.status || '')}">
                        <div class="cell-content">
                            ${task.status ? `<span class="status-badge" style="background:${statusStyle.bg};color:${statusStyle.text}">${task.status}</span>` : '<span class="empty-cell">-</span>'}
                        </div>
                    </td>
                    <td onclick="editCell(this, 'deadline', 'date')" data-prop="deadline" data-value="${task.deadline || ''}">
                        <div class="cell-content">${task.deadline ? formatDate(task.deadline) : '<span class="empty-cell">-</span>'}</div>
                    </td>
                    <td onclick="editCell(this, 'prioridade', 'select')" data-prop="prioridade" data-value="${escapeHtml(task.prioridade || '')}">
                        <div class="cell-content">
                            ${task.prioridade ? `<span class="priority-badge" style="background:${prioStyle.bg};color:${prioStyle.text}">${task.prioridade}</span>` : '<span class="empty-cell">-</span>'}
                        </div>
                    </td>
                    <td>
                        <button class="delete-btn" onclick="deleteTask('${task.id}', event)" title="Excluir">✕</button>
                    </td>
                </tr>
            `;
        }

        // Sober emojis for people (consistent per person) - defined early for use in multiple functions
        const personEmojis = ['◆', '◇', '●', '○', '■', '□', '▲', '△', '★', '☆', '◈', '◉', '◎', '⬡', '⬢'];
        function getPersonEmoji(name, idx) {
            // Use first letter hash for consistency
            const hash = name.charCodeAt(0) + (name.charCodeAt(1) || 0);
            return personEmojis[hash % personEmojis.length];
        }

        // Get relation name from schema
        function getRelationName(propName, ids) {
            if (!ids || ids.length === 0) return '';
            if (!notionSchema?.relations?.[propName]?.items) return `[${ids.length}]`;

            const items = notionSchema.relations[propName].items;
            const names = ids.map(id => {
                const item = items.find(i => i.id === id);
                return item ? item.name : id.substring(0, 8);
            });
            return names.join(', ');
        }

        // Get names for multi-select people (Responsavel) with emojis
        function getMultiRelationNames(propName, ids) {
            if (!ids || ids.length === 0) return '';

            // Try workspace people first
            const people = notionSchema?.people || [];
            if (people.length > 0) {
                const names = ids.map(id => {
                    const person = people.find(p => p.id === id);
                    if (!person) return '';
                    const emoji = getPersonEmoji(person.name, people.indexOf(person));
                    return emoji + ' ' + person.name;
                }).filter(Boolean);
                if (names.length > 0) return names.join(', ');
            }

            // Fallback to relations
            return getRelationName(propName, ids);
        }

        // Edit cell - make it editable
        function editCell(td, prop, type) {
            if (currentEditingCell) {
                cancelEdit();
            }

            currentEditingCell = td;
            td.classList.add('editing');

            const taskId = td.parentElement.dataset.taskId;
            const currentValue = td.dataset.value || '';
            const currentIds = (td.dataset.ids || '').split(',').filter(Boolean);

            if (type === 'text') {
                td.innerHTML = `<input type="text" value="${escapeHtml(currentValue)}"
                    onblur="saveCell(this, '${taskId}', '${prop}', 'text')"
                    onkeydown="handleKeydown(event, this, '${taskId}', '${prop}', 'text')"
                    autofocus>`;
                td.querySelector('input').focus();
                td.querySelector('input').select();

            } else if (type === 'date') {
                td.innerHTML = `<input type="date" value="${currentValue}"
                    onchange="saveCell(this, '${taskId}', '${prop}', 'date')"
                    onblur="cancelEdit()"
                    onkeydown="if(event.key==='Escape')cancelEdit()">`;
                td.querySelector('input').focus();

            } else if (type === 'select') {
                // Use custom dropdown for selects (Status, Prioridade)
                const options = notionSchema?.selects?.[capitalizeFirst(prop)] || [];

                // Color mapping for status/priority
                const colorMap = {
                    // Status colors
                    'Concluído': { bg: '#2ecc71', text: '#fff' },
                    'Em andamento': { bg: '#3498db', text: '#fff' },
                    'Pendente': { bg: '#f39c12', text: '#000' },
                    'Bloqueado': { bg: '#e74c3c', text: '#fff' },
                    'Cancelado': { bg: '#95a5a6', text: '#fff' },
                    // Priority colors
                    'Urgente': { bg: '#e74c3c', text: '#fff' },
                    'Alta': { bg: '#e67e22', text: '#fff' },
                    'Média': { bg: '#f1c40f', text: '#000' },
                    'Baixa': { bg: '#2ecc71', text: '#fff' },
                };

                td.innerHTML = `
                    <div class="searchable-dropdown select-dropdown">
                        <input type="text" value="${escapeHtml(currentValue)}" placeholder="Selecione..."
                            oninput="filterSelectDropdown(this, '${prop}')"
                            onfocus="showSelectDropdown(this, '${prop}')"
                            onkeydown="if(event.key==='Escape')cancelEdit()"
                            readonly
                            style="cursor: pointer;">
                        <div class="dropdown-list select-list" id="dropdown-${prop}" style="display:block;">
                            <div class="dropdown-item" data-value="" onclick="selectSelectItem(this, '${taskId}', '${prop}')">
                                <span style="color: var(--text-muted);">- Nenhum -</span>
                            </div>
                            ${options.map(opt => {
                                const color = colorMap[opt.name] || { bg: 'var(--bg-tertiary)', text: 'var(--text-primary)' };
                                return `
                                    <div class="dropdown-item ${opt.name === currentValue ? 'selected' : ''}"
                                        data-value="${escapeHtml(opt.name)}"
                                        onclick="selectSelectItem(this, '${taskId}', '${prop}')">
                                        <span class="select-badge" style="background:${color.bg};color:${color.text};padding:2px 8px;border-radius:4px;font-size:0.85rem;">${opt.name}</span>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    </div>
                `;
                td.querySelector('input').focus();

            } else if (type === 'relation') {
                const notionProp = { 'caso': 'Caso', 'cliente': 'Cliente' }[prop] || prop;
                const items = notionSchema?.relations?.[notionProp]?.items || [];

                createSearchableDropdown(td, taskId, prop, items, currentIds, false);

            } else if (type === 'people') {
                const items = notionSchema?.people || [];
                createSearchableDropdown(td, taskId, prop, items, currentIds, true);
            }
        }

        // Create searchable dropdown for relations (supports multi-select)
        function createSearchableDropdown(td, taskId, prop, items, selectedIds, multiSelect = false) {
            const isPeople = prop === 'responsavel';
            const selectedNames = selectedIds.map(id => {
                const item = items.find(i => i.id === id);
                if (!item) return '';
                const emoji = isPeople ? getPersonEmoji(item.name, items.indexOf(item)) + ' ' : '';
                return emoji + item.name;
            }).filter(Boolean).join(', ');

            td.dataset.multiSelect = multiSelect;
            td.dataset.selectedIds = selectedIds.join(',');

            td.innerHTML = `
                <div class="searchable-dropdown">
                    <input type="text" value="" placeholder="${selectedNames || 'Buscar...'}"
                        oninput="filterDropdown(this, '${prop}')"
                        onkeydown="handleDropdownKeydown(event, this, '${taskId}', '${prop}')"
                        onfocus="showDropdown(this, '${prop}')"
                        autofocus>
                    <div class="dropdown-list" id="dropdown-${prop}" style="display:none;">
                        ${items.map((item, idx) => {
                            const emoji = isPeople ? getPersonEmoji(item.name, idx) + ' ' : '';
                            return `
                            <div class="dropdown-item ${selectedIds.includes(item.id) ? 'selected' : ''}"
                                data-id="${item.id}" data-name="${escapeHtml(item.name)}" data-email="${escapeHtml(item.email || '')}" data-index="${idx}"
                                onclick="selectDropdownItem(this, '${taskId}', '${prop}', ${multiSelect})">
                                ${multiSelect ? `<span class="checkbox">${selectedIds.includes(item.id) ? '☑' : '☐'}</span> ` : ''}${emoji}${item.name}
                            </div>
                        `}).join('')}
                        ${items.length === 0 ? '<div class="dropdown-item no-results">Nenhum item encontrado</div>' : ''}
                        ${multiSelect ? `<div class="dropdown-confirm" onclick="confirmMultiSelect('${taskId}', '${prop}')">✓ Confirmar</div>` : ''}
                    </div>
                </div>
            `;
            td.querySelector('input').focus();
        }

        // Show dropdown
        function showDropdown(input, prop) {
            const dropdown = document.getElementById(`dropdown-${prop}`);
            if (dropdown) dropdown.style.display = 'block';
        }

        // Show select dropdown (for status/prioridade)
        function showSelectDropdown(input, prop) {
            const dropdown = document.getElementById(`dropdown-${prop}`);
            if (dropdown) dropdown.style.display = 'block';
        }

        // Filter select dropdown
        function filterSelectDropdown(input, prop) {
            // For readonly selects, just show all options
            const dropdown = document.getElementById(`dropdown-${prop}`);
            if (dropdown) dropdown.style.display = 'block';
        }

        // Select item from status/prioridade dropdown
        async function selectSelectItem(item, taskId, prop) {
            const value = item.dataset.value || '';
            const td = currentEditingCell;

            if (!td) return;

            td.classList.remove('editing');
            td.classList.add('saving');

            // Update display immediately
            const colorMap = {
                'Concluído': { bg: '#2ecc71', text: '#fff' },
                'Em andamento': { bg: '#3498db', text: '#fff' },
                'Pendente': { bg: '#f39c12', text: '#000' },
                'Bloqueado': { bg: '#e74c3c', text: '#fff' },
                'Cancelado': { bg: '#95a5a6', text: '#fff' },
                'Urgente': { bg: '#e74c3c', text: '#fff' },
                'Alta': { bg: '#e67e22', text: '#fff' },
                'Média': { bg: '#f1c40f', text: '#000' },
                'Baixa': { bg: '#2ecc71', text: '#fff' },
            };
            const style = colorMap[value] || { bg: '#2d2d2d', text: '#9b9b9b' };
            const badgeClass = prop === 'status' ? 'status-badge' : 'priority-badge';
            td.innerHTML = value ?
                `<div class="cell-content"><span class="${badgeClass}" style="background:${style.bg};color:${style.text}">${value}</span></div>` :
                '<div class="cell-content"><span class="empty-cell">-</span></div>';
            td.dataset.value = value;

            try {
                const token = localStorage.getItem('ilc_access_token');
                const response = await fetch(`api/tasks/${taskId}`, {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({ [prop]: value || null })
                });

                if (!response.ok) {
                    throw new Error('Failed to save');
                }
            } catch (error) {
                console.error('Save error:', error);
                td.innerHTML = '<div class="cell-content" style="color:var(--error)">Erro!</div>';
            } finally {
                td.classList.remove('saving');
                currentEditingCell = null;
            }
        }

        // Filter dropdown items
        function filterDropdown(input, prop) {
            const filter = input.value.toLowerCase();
            const dropdown = document.getElementById(`dropdown-${prop}`);
            if (!dropdown) return;

            dropdown.style.display = 'block';
            const items = dropdown.querySelectorAll('.dropdown-item:not(.no-results):not(.dropdown-confirm)');
            let hasVisible = false;

            items.forEach(item => {
                const name = item.dataset.name?.toLowerCase() || '';
                if (name.includes(filter)) {
                    item.style.display = 'block';
                    hasVisible = true;
                } else {
                    item.style.display = 'none';
                }
            });
        }

        // Handle dropdown keyboard navigation
        function handleDropdownKeydown(event, input, taskId, prop) {
            if (event.key === 'Escape') {
                cancelEdit();
            } else if (event.key === 'Enter') {
                const dropdown = document.getElementById(`dropdown-${prop}`);
                const visible = dropdown?.querySelectorAll('.dropdown-item:not(.no-results):not(.dropdown-confirm)[style*="display: block"], .dropdown-item:not(.no-results):not(.dropdown-confirm):not([style])');
                if (visible && visible.length > 0) {
                    selectDropdownItem(visible[0], taskId, prop);
                }
            }
        }

        // Select dropdown item (toggle for multi-select)
        function selectDropdownItem(item, taskId, prop, multiSelect = false) {
            const id = item.dataset.id;
            const name = item.dataset.name;

            if (!id) return;

            const td = currentEditingCell;

            if (multiSelect) {
                let selectedIds = (td.dataset.selectedIds || '').split(',').filter(Boolean);
                const checkbox = item.querySelector('.checkbox');

                if (selectedIds.includes(id)) {
                    selectedIds = selectedIds.filter(i => i !== id);
                    item.classList.remove('selected');
                    if (checkbox) checkbox.textContent = '☐';
                } else {
                    selectedIds.push(id);
                    item.classList.add('selected');
                    if (checkbox) checkbox.textContent = '☑';
                }

                td.dataset.selectedIds = selectedIds.join(',');
            } else {
                saveRelationSelection(td, taskId, prop, [id], name);
            }
        }

        // Confirm multi-select and save
        async function confirmMultiSelect(taskId, prop) {
            const td = currentEditingCell;
            const selectedIds = (td.dataset.selectedIds || '').split(',').filter(Boolean);

            const items = notionSchema?.people || [];
            const isPeople = prop === 'responsavel';
            const names = selectedIds.map(id => {
                const item = items.find(i => i.id === id);
                if (!item) return '';
                const emoji = isPeople ? getPersonEmoji(item.name, items.indexOf(item)) + ' ' : '';
                return emoji + item.name;
            }).filter(Boolean).join(', ');

            await saveRelationSelection(td, taskId, prop, selectedIds, names, true);
        }

        // Save relation/people selection
        async function saveRelationSelection(td, taskId, prop, ids, displayName, sendEmail = false) {
            td.classList.remove('editing');
            td.classList.add('saving');
            td.innerHTML = `<div class="cell-content">${displayName || '<span class="empty-cell">-</span>'}</div>`;

            try {
                const token = localStorage.getItem('ilc_access_token');
                const response = await fetch(`api/tasks/${taskId}`, {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({
                        property: prop,
                        relation_ids: ids,
                        send_email: sendEmail
                    })
                });

                if (!response.ok) throw new Error('Failed to save');

                td.dataset.ids = ids.join(',');
                td.classList.remove('saving');
                currentEditingCell = null;

                const index = td.parentElement.dataset.index;
                if (tasksData[index]) {
                    tasksData[index][prop] = { name: displayName, ids: ids };
                }

            } catch (error) {
                console.error('Save error:', error);
                td.classList.remove('saving');
                td.innerHTML = `<div class="cell-content" style="color:var(--error)">Erro!</div>`;
                setTimeout(() => loadTasks(), 1500);
            }
        }

        // Save cell value
        async function saveCell(input, taskId, prop, type) {
            const value = input.value;
            const td = currentEditingCell;

            if (!td) return;

            td.classList.remove('editing');
            td.classList.add('saving');

            if (type === 'select' && prop === 'status') {
                const style = statusColors[value] || { bg: '#2d2d2d', text: '#9b9b9b' };
                td.innerHTML = value ? `<div class="cell-content"><span class="status-badge" style="background:${style.bg};color:${style.text}">${value}</span></div>` : '<div class="cell-content"><span class="empty-cell">-</span></div>';
            } else if (type === 'select' && prop === 'prioridade') {
                const style = priorityColors[value] || { bg: '#2d2d2d', text: '#9b9b9b' };
                td.innerHTML = value ? `<div class="cell-content"><span class="priority-badge" style="background:${style.bg};color:${style.text}">${value}</span></div>` : '<div class="cell-content"><span class="empty-cell">-</span></div>';
            } else if (type === 'date') {
                td.innerHTML = `<div class="cell-content">${value ? formatDate(value) : '<span class="empty-cell">-</span>'}</div>`;
            } else {
                td.innerHTML = `<div class="cell-content">${value || '<span class="empty-cell">-</span>'}</div>`;
            }

            try {
                const token = localStorage.getItem('ilc_access_token');
                const response = await fetch(`api/tasks/${taskId}`, {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({ property: prop, value: value || null })
                });

                if (!response.ok) throw new Error('Failed to save');

                td.dataset.value = value;
                td.classList.remove('saving');
                currentEditingCell = null;

                const index = td.parentElement.dataset.index;
                if (tasksData[index]) {
                    tasksData[index][prop] = value;
                }

            } catch (error) {
                console.error('Save error:', error);
                td.classList.remove('saving');
                td.innerHTML = `<div class="cell-content" style="color:var(--error)">Erro ao salvar!</div>`;
                setTimeout(() => loadTasks(), 1500);
            }
        }

        // Handle keyboard in text input
        function handleKeydown(event, input, taskId, prop, type) {
            if (event.key === 'Enter') {
                input.blur();
            } else if (event.key === 'Escape') {
                cancelEdit();
            }
        }

        // Cancel editing
        function cancelEdit() {
            if (!currentEditingCell) return;

            const td = currentEditingCell;
            const prop = td.dataset.prop;
            const value = td.dataset.value || '';
            const ids = (td.dataset.ids || '').split(',').filter(Boolean);

            if (prop === 'status') {
                const style = statusColors[value] || { bg: '#2d2d2d', text: '#9b9b9b' };
                td.innerHTML = value ? `<div class="cell-content"><span class="status-badge" style="background:${style.bg};color:${style.text}">${value}</span></div>` : '<div class="cell-content"><span class="empty-cell">-</span></div>';
            } else if (prop === 'prioridade') {
                const style = priorityColors[value] || { bg: '#2d2d2d', text: '#9b9b9b' };
                td.innerHTML = value ? `<div class="cell-content"><span class="priority-badge" style="background:${style.bg};color:${style.text}">${value}</span></div>` : '<div class="cell-content"><span class="empty-cell">-</span></div>';
            } else if (prop === 'deadline') {
                td.innerHTML = `<div class="cell-content">${value ? formatDate(value) : '<span class="empty-cell">-</span>'}</div>`;
            } else if (['pessoa', 'responsavel', 'caso', 'cliente'].includes(prop)) {
                const notionProp = { 'pessoa': 'Pessoa', 'responsavel': 'Responsável', 'caso': 'Caso', 'cliente': 'Cliente' }[prop];
                const name = getRelationName(notionProp, ids);
                td.innerHTML = `<div class="cell-content">${name || '<span class="empty-cell">-</span>'}</div>`;
            } else {
                td.innerHTML = `<div class="cell-content">${value || '<span class="empty-cell">-</span>'}</div>`;
            }

            td.classList.remove('editing');
            currentEditingCell = null;
        }

        // Delete task
        async function deleteTask(taskId, event) {
            event.stopPropagation();

            if (!confirm('Tem certeza que deseja excluir esta tarefa?')) return;

            try {
                const token = localStorage.getItem('ilc_access_token');
                const response = await fetch(`api/tasks/${taskId}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (response.ok) {
                    loadTasks();
                } else {
                    alert('Erro ao excluir tarefa');
                }
            } catch (error) {
                console.error('Delete error:', error);
                alert('Erro ao excluir tarefa');
            }
        }

        // Add new task
        async function addNewTask() {
            const title = prompt('Nome da nova tarefa:');
            if (!title) return;

            try {
                const token = localStorage.getItem('ilc_access_token');
                const response = await fetch('api/tasks', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({ title, assignee: 'admin@casehub.legal' })
                });

                if (response.ok) {
                    loadTasks();
                } else {
                    alert('Erro ao criar tarefa');
                }
            } catch (error) {
                console.error('Create error:', error);
                alert('Erro ao criar tarefa');
            }
        }

        // ==================== KANBAN ====================
        let currentViewMode = localStorage.getItem('tasksViewMode') || 'list';
        const kanbanStatusConfig = {
            'A fazer': { color: '#9b9b9b', bg: '#2d2d2d', emoji: '📋' },
            'Em andamento': { color: '#a78bfa', bg: '#3d3a50', emoji: '🔄' },
            'Concluido': { color: '#4ade80', bg: '#1d3a2f', emoji: '✅' },
            'Cancelado': { color: '#f87171', bg: '#3d2d2d', emoji: '❌' }
        };

        function switchView(mode) {
            currentViewMode = mode;
            localStorage.setItem('tasksViewMode', mode);
            const listContainer = document.getElementById('list-container');
            const kanbanContainer = document.getElementById('kanban-container');
            document.getElementById('view-list').classList.toggle('active', mode === 'list');
            document.getElementById('view-kanban').classList.toggle('active', mode === 'kanban');
            if (mode === 'list') {
                listContainer.style.display = 'block';
                kanbanContainer.style.display = 'none';
            } else {
                listContainer.style.display = 'none';
                kanbanContainer.style.display = 'block';
                renderKanbanBoard();
            }
        }

        function renderKanbanBoard() {
            if (!tasksData || tasksData.length === 0) {
                document.getElementById('kanban-board').innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:3rem;color:var(--text-secondary);">Nenhuma tarefa</div>';
                return;
            }
            const groups = {};
            Object.keys(kanbanStatusConfig).forEach(s => groups[s] = []);
            tasksData.forEach(t => {
                const s = t.status || 'A fazer';
                (groups[s] || groups['A fazer']).push(t);
            });
            let html = '';
            Object.entries(kanbanStatusConfig).forEach(([status, cfg]) => {
                const tasks = groups[status] || [];
                html += `<div class="kanban-column" data-status="${status}">
                    <div class="kanban-column-header" style="background:${cfg.bg};">
                        <div class="kanban-column-title"><span class="status-dot" style="background:${cfg.color};"></span>${status}</div>
                        <span class="kanban-column-count">${tasks.length}</span>
                    </div>
                    <div class="kanban-column-cards" data-status="${status}">
                        ${tasks.length > 0 ? tasks.map(t => renderKanbanCard(t)).join('') : `<div class="kanban-column-empty"><span>${cfg.emoji}</span>Nenhuma</div>`}
                    </div>
                </div>`;
            });
            document.getElementById('kanban-board').innerHTML = html;
            initDragAndDrop();
        }

        function renderKanbanCard(task) {
            const resp = getMultiRelationNames('Responsável', task.responsavel?.ids) || '-';
            const cli = getRelationName('Cliente', task.cliente?.ids) || '';
            const prio = task.prioridade || 'Media';
            const pc = priorityColors[prio] || {bg:'#2d2d2d',text:'#9b9b9b'};
            let dl = '';
            if (task.deadline) {
                const dd = new Date(task.deadline+'T00:00:00'), td = new Date(); td.setHours(0,0,0,0);
                const diff = Math.floor((dd-td)/(1000*60*60*24));
                dl = `<span class="deadline ${diff<0?'overdue':''}">📅 ${formatDate(task.deadline)}</span>`;
            }
            return `<div class="kanban-card" data-task-id="${task.id}" draggable="true">
                <div class="kanban-card-header">
                    <div class="kanban-card-title"><a href="${task.url||'#'}" target="_blank">${escapeHtml(task.tarefa)}</a></div>
                    <button class="kanban-card-delete" onclick="deleteTask('${task.id}',event)">✕</button>
                </div>
                <div class="kanban-card-meta">
                    <span class="badge responsavel">${resp}</span>
                    ${cli ? `<span class="badge cliente">${cli}</span>` : ''}
                </div>
                <div class="kanban-card-footer">
                    <span class="priority-badge" style="background:${pc.bg};color:${pc.text};">${prio}</span>
                    ${dl}
                </div>
            </div>`;
        }

        let draggedCard = null;
        function initDragAndDrop() {
            document.querySelectorAll('.kanban-card').forEach(c => {
                c.addEventListener('dragstart', e => { draggedCard = e.target; e.target.classList.add('dragging'); });
                c.addEventListener('dragend', e => { e.target.classList.remove('dragging'); draggedCard = null; });
            });
            document.querySelectorAll('.kanban-column-cards').forEach(col => {
                col.addEventListener('dragover', e => { e.preventDefault(); col.classList.add('drag-over'); });
                col.addEventListener('dragleave', e => col.classList.remove('drag-over'));
                col.addEventListener('drop', async e => {
                    e.preventDefault(); col.classList.remove('drag-over');
                    if (!draggedCard) return;
                    const taskId = draggedCard.dataset.taskId;
                    const newStatus = col.dataset.status;
                    const oldCol = draggedCard.closest('.kanban-column');
                    if (oldCol?.dataset.status === newStatus) return;
                    const empty = col.querySelector('.kanban-column-empty');
                    if (empty) empty.remove();
                    col.appendChild(draggedCard);
                    document.querySelectorAll('.kanban-column').forEach(c => {
                        c.querySelector('.kanban-column-count').textContent = c.querySelectorAll('.kanban-card').length;
                    });
                    try {
                        draggedCard.classList.add('saving');
                        const r = await fetch(`/api/tasks/${taskId}`, {
                            method: 'PATCH',
                            headers: {'Content-Type':'application/json'},
                            body: JSON.stringify({property:'status',value:newStatus})
                        });
                        if (!r.ok) throw new Error();
                        draggedCard.classList.remove('saving');
                        const t = tasksData.find(x => x.id === taskId);
                        if (t) t.status = newStatus;
                    } catch(err) {
                        draggedCard.classList.remove('saving');
                        renderKanbanBoard();
                        alert('Erro ao atualizar');
                    }
                });
            });
        }

        function initTasksView() {
            if (currentViewMode === 'kanban') switchView('kanban');
        }
        // ==================== FIM KANBAN ====================

        // Filter tasks table
        function filterTasksTable() {
            const filter = document.getElementById('tasks-search').value.toLowerCase();
            const rows = document.querySelectorAll('#tasks-tbody tr');

            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(filter) ? '' : 'none';
            });
        }

        // Utility functions for tasks
        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function formatDate(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr + 'T00:00:00');
            return date.toLocaleDateString('pt-BR');
        }

        function capitalizeFirst(str) {
            if (!str) return '';
            const map = { 'tarefa': 'Tarefa', 'pessoa': 'Pessoa', 'responsavel': 'Responsável', 'caso': 'Caso', 'cliente': 'Cliente', 'status': 'Status', 'deadline': 'Deadline', 'prioridade': 'Prioridade' };
            return map[str] || str.charAt(0).toUpperCase() + str.slice(1);
        }

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            // Don't close if clicking inside the editing cell or dropdown
            if (e.target.closest('.searchable-dropdown') ||
                e.target.closest('.dropdown-item') ||
                e.target.closest('.dropdown-confirm') ||
                e.target.closest('.editing') ||
                e.target.tagName === 'INPUT' ||
                e.target.tagName === 'SELECT') {
                return;
            }
            // Small delay to allow click handlers to run first
            setTimeout(() => {
                document.querySelectorAll('.dropdown-list').forEach(d => d.style.display = 'none');
            }, 150);
        });

        // Initialize tasks when section is shown
        const originalShowSection = window.showSection;
        window.showSection = function(section, updateHash = true) {
            originalShowSection(section, updateHash);
            if (section === 'tasks') {
                if (!notionSchema) {
                    loadNotionSchema().then(() => { loadTasks(); initTasksView(); });
                } else {
                    loadTasks();
                    initTasksView();
                }
            }
        };

// Toggle between list and kanban view
function switchView(view) {
    const listBtn = document.getElementById("view-list");
    const kanbanBtn = document.getElementById("view-kanban");
    const container = document.querySelector("#tasks-container, .tasks-list, #tasksList");
    
    if (!container) {
        console.warn("Tasks container not found");
        return;
    }
    
    if (view === "list") {
        container.classList.remove("kanban-view");
        container.classList.add("list-view");
        if (listBtn) listBtn.classList.add("active");
        if (kanbanBtn) kanbanBtn.classList.remove("active");
        localStorage.setItem("tasksView", "list");
    } else if (view === "kanban") {
        container.classList.remove("list-view");
        container.classList.add("kanban-view");
        if (kanbanBtn) kanbanBtn.classList.add("active");
        if (listBtn) listBtn.classList.remove("active");
        localStorage.setItem("tasksView", "kanban");
    }
}

// Restore saved view on page load
document.addEventListener("DOMContentLoaded", () => {
    const savedView = localStorage.getItem("tasksView") || "list";
    if (typeof switchView === "function") {
        switchView(savedView);
    }
});
