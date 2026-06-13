/**
 * Script to match emails from Moskit CSV export with active clients
 */

const fs = require('fs');
const path = require('path');

// Read CSV file
const csvPath = '/Users/beijaflor/Downloads/698fed65-5863-48a4-8ffb-1e7b045a1175.csv';
const clientsPath = path.join(__dirname, 'active-clients.json');

// Parse CSV line (handles quoted fields with commas)
function parseCSVLine(line) {
  const fields = [];
  let field = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];

    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      fields.push(field.trim());
      field = '';
    } else {
      field += char;
    }
  }
  fields.push(field.trim());

  return fields;
}

// Normalize name for comparison
function normalizeName(name) {
  if (!name) return '';
  return name
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') // Remove accents
    .replace(/[^a-z\s]/g, '') // Remove non-letters
    .replace(/\s+/g, ' ')
    .trim();
}

// Main function
async function matchEmails() {
  console.log('Loading CSV...');
  const csvContent = fs.readFileSync(csvPath, 'utf8');
  const lines = csvContent.split('\n');

  console.log(`CSV has ${lines.length} lines`);

  // Parse header
  const header = parseCSVLine(lines[0]);
  const nameIndex = header.findIndex(h => h === 'Nome');
  const emailIndex = header.findIndex(h => h === 'Emails');

  console.log(`Name column index: ${nameIndex}, Email column index: ${emailIndex}`);

  // Build map of normalized names to emails
  const emailMap = new Map();
  const nameVariants = new Map(); // Store original names for each normalized name

  for (let i = 1; i < lines.length; i++) {
    if (!lines[i].trim()) continue;

    const fields = parseCSVLine(lines[i]);
    const name = fields[nameIndex];
    const email = fields[emailIndex];

    if (name && email) {
      const normalized = normalizeName(name);
      if (normalized && !emailMap.has(normalized)) {
        emailMap.set(normalized, email);
        nameVariants.set(normalized, name);
      }
    }
  }

  console.log(`Found ${emailMap.size} contacts with emails in CSV`);

  // Load active clients
  const clientsData = JSON.parse(fs.readFileSync(clientsPath, 'utf8'));
  console.log(`Active clients: ${clientsData.clients.length}`);

  // Match emails
  let matched = 0;
  let notFound = [];

  for (const client of clientsData.clients) {
    const normalized = normalizeName(client.name);

    // Try exact match first
    if (emailMap.has(normalized)) {
      client.email = emailMap.get(normalized);
      matched++;
      console.log(`✓ ${client.name} -> ${client.email}`);
    } else {
      // Try partial match (first + last name)
      let found = false;
      const clientParts = normalized.split(' ');

      for (const [csvNormalized, csvEmail] of emailMap) {
        const csvParts = csvNormalized.split(' ');

        // Match if first and last name match
        if (clientParts.length >= 2 && csvParts.length >= 2) {
          if (clientParts[0] === csvParts[0] &&
              clientParts[clientParts.length - 1] === csvParts[csvParts.length - 1]) {
            client.email = csvEmail;
            matched++;
            found = true;
            console.log(`✓ ${client.name} ~> ${nameVariants.get(csvNormalized)} -> ${client.email}`);
            break;
          }
        }

        // Match if one name contains the other
        if (!found && (csvNormalized.includes(normalized) || normalized.includes(csvNormalized))) {
          if (clientParts[0] === csvParts[0]) { // First name must match
            client.email = csvEmail;
            matched++;
            found = true;
            console.log(`✓ ${client.name} ≈> ${nameVariants.get(csvNormalized)} -> ${client.email}`);
            break;
          }
        }
      }

      if (!found) {
        notFound.push(client.name);
      }
    }
  }

  console.log('\n========== RESULTS ==========');
  console.log(`Matched: ${matched}/${clientsData.clients.length}`);
  console.log(`Not found: ${notFound.length}`);

  if (notFound.length > 0) {
    console.log('\nClients without email match:');
    notFound.forEach(name => console.log(`  - ${name}`));
  }

  // Save updated clients
  clientsData.lastUpdated = new Date().toISOString().split('T')[0];
  fs.writeFileSync(clientsPath, JSON.stringify(clientsData, null, 2));
  console.log('\n✓ Saved updated active-clients.json');

  // Show summary of clients with emails
  const withEmail = clientsData.clients.filter(c => c.email).length;
  console.log(`\nFinal: ${withEmail}/${clientsData.clients.length} clients have emails`);
}

matchEmails().catch(console.error);
