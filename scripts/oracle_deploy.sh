#!/bin/bash
# CaseHub White-Label - Oracle Cloud Deploy Script
# Usage: bash scripts/oracle_deploy.sh
# Requires: oci-cli configured (~/.oci/config)

set -e
export PATH="$HOME/Library/Python/3.9/bin:$PATH"
export SUPPRESS_LABEL_WARNING=True

TENANCY="ocid1.tenancy.oc1..aaaaaaaaclaqqr76twdfseeefqnzxdsyjhbrmho4xpohorbsrwfjtiz3nd6a"
SSH_KEY="$HOME/.oci/casehub_ssh_key"
SSH_PUB=$(cat "$SSH_KEY.pub")

# Regions to try (in order of preference)
REGIONS=("sa-vinhedo-1" "sa-santiago-1" "us-ashburn-1" "sa-saopaulo-1")

echo "========================================="
echo "  CaseHub White-Label - Oracle Deploy"
echo "========================================="

# Step 1: Find a region with ARM capacity
for REGION in "${REGIONS[@]}"; do
    echo ""
    echo ">>> Trying region: $REGION"

    # Check if subscribed
    SUBSCRIBED=$(oci iam region-subscription list --tenancy-id "$TENANCY" --output json 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)['data']
for r in data:
    if r['region-name'] == '$REGION' and r['status'] == 'READY':
        print('YES')
        break
else:
    print('NO')
" 2>/dev/null || echo "NO")

    if [ "$SUBSCRIBED" != "YES" ]; then
        echo "    Not subscribed to $REGION, subscribing..."
        oci iam region-subscription create --tenancy-id "$TENANCY" --region-key "$(echo $REGION | cut -d'-' -f1-2 | tr '[:lower:]' '[:upper:]' | tr '-' '')" 2>/dev/null || true
        echo "    Waiting 30s for subscription to propagate..."
        sleep 30
    fi

    # Get AD
    AD=$(oci iam availability-domain list --compartment-id "$TENANCY" --region "$REGION" --output json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['data'][0]['name'])" 2>/dev/null || echo "FAIL")

    if [ "$AD" = "FAIL" ]; then
        echo "    Region not ready yet, skipping..."
        continue
    fi
    echo "    AD: $AD"

    # Get Ubuntu ARM image
    IMAGE_ID=$(oci compute image list --compartment-id "$TENANCY" --region "$REGION" --operating-system "Canonical Ubuntu" --operating-system-version "22.04" --shape "VM.Standard.A1.Flex" --output json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null || echo "FAIL")

    if [ "$IMAGE_ID" = "FAIL" ]; then
        echo "    No ARM image found, skipping..."
        continue
    fi

    # Create VCN
    echo "    Creating network..."
    VCN_ID=$(oci network vcn list --compartment-id "$TENANCY" --region "$REGION" --display-name "casehub-vcn" --output json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print(d[0]['id'] if d else 'NONE')" 2>/dev/null || echo "NONE")

    if [ "$VCN_ID" = "NONE" ]; then
        VCN_ID=$(oci network vcn create --compartment-id "$TENANCY" --region "$REGION" --cidr-blocks '["10.0.0.0/16"]' --display-name "casehub-vcn" --dns-label "casehubvcn" --output json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['id'])")

        # Internet Gateway
        IGW_ID=$(oci network internet-gateway create --compartment-id "$TENANCY" --region "$REGION" --vcn-id "$VCN_ID" --display-name "casehub-igw" --is-enabled true --output json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['id'])")

        # Route table
        RT_ID=$(oci network route-table list --compartment-id "$TENANCY" --region "$REGION" --vcn-id "$VCN_ID" --output json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['data'][0]['id'])")
        oci network route-table update --region "$REGION" --rt-id "$RT_ID" --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW_ID\"}]" --force 2>/dev/null >/dev/null

        # Security list
        SL_ID=$(oci network security-list create --compartment-id "$TENANCY" --region "$REGION" --vcn-id "$VCN_ID" --display-name "casehub-sl" \
          --ingress-security-rules '[{"source":"0.0.0.0/0","protocol":"6","tcpOptions":{"destinationPortRange":{"min":22,"max":22}}},{"source":"0.0.0.0/0","protocol":"6","tcpOptions":{"destinationPortRange":{"min":80,"max":80}}},{"source":"0.0.0.0/0","protocol":"6","tcpOptions":{"destinationPortRange":{"min":443,"max":443}}},{"source":"0.0.0.0/0","protocol":"6","tcpOptions":{"destinationPortRange":{"min":8001,"max":8001}}}]' \
          --egress-security-rules '[{"destination":"0.0.0.0/0","protocol":"all"}]' --output json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['id'])")

        # Subnet
        SUBNET_ID=$(oci network subnet create --compartment-id "$TENANCY" --region "$REGION" --vcn-id "$VCN_ID" --cidr-block "10.0.1.0/24" --display-name "casehub-subnet" --dns-label "casehubsub" --availability-domain "$AD" --security-list-ids "[\"$SL_ID\"]" --route-table-id "$RT_ID" --output json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['id'])")
    else
        SUBNET_ID=$(oci network subnet list --compartment-id "$TENANCY" --region "$REGION" --vcn-id "$VCN_ID" --output json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['data'][0]['id'])")
    fi

    # Launch VM
    echo "    Launching VM (2 OCPU, 12GB ARM)..."
    RESULT=$(oci compute instance launch \
      --compartment-id "$TENANCY" \
      --region "$REGION" \
      --availability-domain "$AD" \
      --shape "VM.Standard.A1.Flex" \
      --shape-config '{"ocpus":2,"memoryInGBs":12}' \
      --image-id "$IMAGE_ID" \
      --subnet-id "$SUBNET_ID" \
      --assign-public-ip true \
      --display-name "casehub-whitelabel" \
      --metadata "{\"ssh_authorized_keys\":\"$SSH_PUB\"}" \
      --output json 2>&1)

    if echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['id'])" 2>/dev/null; then
        INSTANCE_ID=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['id'])")
        echo ""
        echo "========================================="
        echo "  VM CREATED SUCCESSFULLY!"
        echo "  Region: $REGION"
        echo "  Instance: $INSTANCE_ID"
        echo "========================================="
        echo ""
        echo "Waiting for public IP..."
        sleep 30

        # Get VNIC and public IP
        VNIC_ID=$(oci compute instance list-vnics --instance-id "$INSTANCE_ID" --region "$REGION" --output json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null || echo "PENDING")
        if [ "$VNIC_ID" != "PENDING" ]; then
            PUBLIC_IP=$(oci network vnic get --vnic-id "$VNIC_ID" --region "$REGION" --output json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['public-ip'])" 2>/dev/null || echo "PENDING")
        else
            PUBLIC_IP="PENDING"
        fi

        echo "  Public IP: $PUBLIC_IP"
        echo ""
        echo "  SSH: ssh -i $SSH_KEY ubuntu@$PUBLIC_IP"
        echo ""
        echo "  Save this info!"
        exit 0
    else
        echo "    Failed: $(echo "$RESULT" | grep -o '"message":[^,]*' | head -1)"
        continue
    fi
done

echo ""
echo "All regions exhausted. Try again in a few minutes."
exit 1
