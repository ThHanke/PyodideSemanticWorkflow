#!/bin/bash

################################################################################
# Update Namespace URIs Script
#
# This script updates all namespace URIs from github.com to github.io
# to make them resolvable via GitHub Pages.
#
# Usage: ./scripts/update-namespaces.sh
#
# Run this after enabling GitHub Pages in your repository settings.
################################################################################

set -e  # Exit on error

echo "🔄 Updating namespace URIs for GitHub Pages..."
echo

# Define old and new namespaces
OLD_NS="https://github.com/ThHanke/PyodideSemanticWorkflow"
NEW_NS="https://thhanke.github.io/PyodideSemanticWorkflow"

# Counter for files updated
count=0

# Find and update all .ttl files
echo "📝 Searching for .ttl files..."
while IFS= read -r -d '' file; do
    if grep -q "$OLD_NS" "$file"; then
        echo "  Updating: $file"
        sed -i "s|$OLD_NS|$NEW_NS|g" "$file"
        ((count++))
    fi
done < <(find . -name "*.ttl" -type f -print0)

echo
echo "✅ Updated $count file(s)"
echo
echo "📋 Next steps:"
echo "  1. Review the changes:"
echo "     git diff"
echo
echo "  2. Commit and push:"
echo "     git add ."
echo "     git commit -m \"Update namespace URIs for GitHub Pages\""
echo "     git push"
echo
echo "  3. Wait 1-2 minutes for GitHub Pages to deploy"
echo
echo "  4. Test your URIs:"
echo "     https://thhanke.github.io/PyodideSemanticWorkflow/"
echo

exit 0
