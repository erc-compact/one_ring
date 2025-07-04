#!/bin/bash
set -euo pipefail

# === Resolve SCRIPT_DIR ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(realpath "$SCRIPT_DIR/..")"
SCRATCH_DIR="$REPO_ROOT/scratch"

# Make sure scratch exists
mkdir -p "$SCRATCH_DIR"

OUTPUT_FILE="$SCRATCH_DIR/docker_image_digests.csv"

# Define images and their versions
declare -A IMAGES
IMAGES["vishnubk/compact_sql"]="latest"
IMAGES["vishnubk/peasoup"]="keplerian"
IMAGES["vishnubk/pulsar-miner"]="turing-sm75"
IMAGES["vishnubk/pulsarx"]="latest"
IMAGES["vishnubk/pics"]="20230630_pics_model_update"
IMAGES["vishnubk/mmgps_candidate_filter"]="20230821-rfi-filter-snr-thresh"
IMAGES["vishnubk/candy_picker"]="latest"
IMAGES["vishnubk/watchdog"]="latest"

#apptainer pull docker://vishnubk/peasoup:latest -> .sif (hash from dockerhub -> docker image)

#Remove OUTPUT_FILE if it exists
rm -rf $OUTPUT_FILE

echo "Username,Image,Version,SHA256" > "$OUTPUT_FILE"

# Function to get digest
get_digest() {
    local image=$1
    local version=$2
    TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:$image:pull" | python -c "import sys, json; print(json.load(sys.stdin)['token'])")
    DIGEST=$(curl -s -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.docker.distribution.manifest.v2+json" -I "https://registry-1.docker.io/v2/$image/manifests/$version" | grep docker-content-digest | awk '{print $2}')
    echo ${DIGEST#"sha256:"}
}

# Iterate over images and versions
for image_with_namespace in "${!IMAGES[@]}"; do
    version=${IMAGES[$image_with_namespace]}
    # Split image name into username and image
    IFS='/' read -r username image <<< "$image_with_namespace"
    # Check if entry is already in the file
    if ! grep -q "$username,$image,$version," "$OUTPUT_FILE"; then
        # Get digest
        digest=$(get_digest $image_with_namespace $version)
        # Append username, image, version, and digest to file
        echo "$username,$image,$version,$digest" >> "$OUTPUT_FILE"
    fi
done

echo "Digests stored/updated in $OUTPUT_FILE"
