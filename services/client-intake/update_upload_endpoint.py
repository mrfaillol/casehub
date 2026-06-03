#!/usr/bin/env python3
"""
Script to update the upload endpoint with LLM classification.
Adds classification call and updates database INSERT.
"""

import sys

def update_app_py(file_path):
    """Update app.py with LLM classification integration."""

    with open(file_path, 'r') as f:
        lines = f.readlines()

    # Find the line with "# Save file"
    insert_after = -1
    for i, line in enumerate(lines):
        if "# Save file" in line and "with open(file_path, 'wb')" in lines[i+1]:
            insert_after = i + 2  # After the "f.write(contents)" line
            break

    if insert_after == -1:
        print("ERROR: Could not find insertion point")
        return False

    # Skip the f.write line
    while insert_after < len(lines) and "f.write" in lines[insert_after]:
        insert_after += 1

    # Insert LLM classification code
    classification_code = """
    # LLM Classification
    try:
        llm_doc_type, classification_confidence = classify_document_with_llm(file.filename, contents[:5000])
        llm_classified = True
    except Exception as e:
        logger.error(f"LLM classification error: {e}")
        llm_doc_type = doc_type
        classification_confidence = 0.5
        llm_classified = False
"""

    # Check if classification code already exists
    code_exists = any("classify_document_with_llm" in line for line in lines[insert_after:insert_after+20])

    if not code_exists:
        lines.insert(insert_after, classification_code)
        print(f"✓ Inserted classification code at line {insert_after}")
    else:
        print("✓ Classification code already exists")

    # Find and update the INSERT statement
    # Look for the INSERT INTO documents line
    insert_start = -1
    insert_end = -1
    for i, line in enumerate(lines):
        if "INSERT INTO documents (" in line:
            insert_start = i
        if insert_start != -1 and "RETURNING id" in line:
            insert_end = i
            break

    if insert_start == -1:
        print("ERROR: Could not find INSERT statement")
        return False

    # Check if already updated
    already_updated = any("llm_classified" in line for line in lines[insert_start:insert_end+5])

    if not already_updated:
        # Replace the old INSERT with new one
        new_insert = """    # Insert into database with PENDING_APPROVAL status and LLM classification
    db.execute(text(\"\"\"
        INSERT INTO documents (
            name, doc_type, status, file_path, file_size, mime_type,
            client_id, case_id, uploaded_via, original_filename, local_path,
            intake_package_id, llm_classified, classification_confidence,
            created_at
        ) VALUES (
            :name, :llm_doc_type, 'PENDING_APPROVAL', :file_path, :file_size, :mime_type,
            :client_id, :case_id, 'client_portal', :original_filename, :local_path,
            :intake_package_id, :llm_classified, :classification_confidence,
            NOW()
        )
        RETURNING id
    \"\"\"), {
        "name": display_name,
        "llm_doc_type": llm_doc_type,
        "file_path": str(file_path),
        "file_size": len(contents),
        "mime_type": file.content_type,
        "client_id": package.client_id,
        "case_id": package.case_id,
        "original_filename": file.filename,
        "local_path": str(file_path),
        "intake_package_id": package.id,
        "llm_classified": llm_classified,
        "classification_confidence": classification_confidence
    })
"""

        # Find the end of the db.execute() call
        exec_end = insert_end
        for i in range(insert_end, min(insert_end + 20, len(lines))):
            if "})" in lines[i]:
                exec_end = i + 1
                break

        # Replace the section
        lines[insert_start:exec_end] = [new_insert + "\n"]
        print(f"✓ Updated INSERT statement (lines {insert_start}-{exec_end})")
    else:
        print("✓ INSERT statement already updated")

    # Write back
    with open(file_path, 'w') as f:
        f.writelines(lines)

    print(f"✓ File updated successfully: {file_path}")
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_upload_endpoint.py <path_to_app.py>")
        sys.exit(1)

    file_path = sys.argv[1]
    success = update_app_py(file_path)
    sys.exit(0 if success else 1)
