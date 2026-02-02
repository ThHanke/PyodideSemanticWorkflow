# GitHub Pages Setup Guide

This guide explains how to enable GitHub Pages for your PyodideSemanticWorkflow repository to make all ontology URIs resolvable.

## 🎯 Goal

Make URIs like `https://thhanke.github.io/PyodideSemanticWorkflow#SumTemplate` resolve to:
- **HTML documentation** for human readers
- **RDF/Turtle** for semantic web agents (content negotiation)

## 📋 Prerequisites

- Repository must be public (or GitHub Pro for private repos)
- You need admin access to the repository

## 🚀 Step 1: Enable GitHub Pages

1. Go to your repository on GitHub: `https://github.com/ThHanke/PyodideSemanticWorkflow`

2. Click on **Settings** (top right)

3. Scroll down to **Pages** (left sidebar under "Code and automation")

4. Under **Source**, select:
   - **Source:** Deploy from a branch
   - **Branch:** `main` (or `master`)
   - **Folder:** `/docs`

5. Click **Save**

6. Wait 1-2 minutes for deployment

7. Your site will be available at: `https://thhanke.github.io/PyodideSemanticWorkflow/`

## 🔄 Step 2: Update Namespace URIs

After GitHub Pages is enabled, you need to update your namespace URIs from:
```turtle
@prefix spw: <https://github.com/ThHanke/PyodideSemanticWorkflow#> .
```

To:
```turtle
@prefix spw: <https://thhanke.github.io/PyodideSemanticWorkflow#> .
```

### Files to Update:
- `ontology/spw.ttl`
- `workflows/catalog.ttl`
- `workflows/catalog-ui.ttl`
- `examples/sum-execution.ttl`
- Any other `.ttl` files using the `spw:` prefix

### Quick Update Script:
```bash
# Run from repository root
find . -name "*.ttl" -type f -exec sed -i 's|https://github.com/ThHanke/PyodideSemanticWorkflow|https://thhanke.github.io/PyodideSemanticWorkflow|g' {} +
```

## 🔗 Step 3: Test URI Resolution

Once GitHub Pages is deployed, test your URIs:

### Test in Browser:
```
https://thhanke.github.io/PyodideSemanticWorkflow#SumTemplate
```
Should redirect to the HTML documentation page.

### Test with Content Negotiation:
```bash
# Request Turtle format
curl -H "Accept: text/turtle" https://thhanke.github.io/PyodideSemanticWorkflow#SumTemplate

# Request RDF/XML
curl -H "Accept: application/rdf+xml" https://thhanke.github.io/PyodideSemanticWorkflow#SumTemplate
```

### Load in RDF Tools:
```python
# Python with rdflib
from rdflib import Graph

g = Graph()
g.parse("https://thhanke.github.io/PyodideSemanticWorkflow/ontology/spw.ttl")
print(len(g))  # Should print number of triples
```

## 📁 File Structure

Your GitHub Pages setup uses this structure:

```
PyodideSemanticWorkflow/
├── docs/                          # GitHub Pages root
│   ├── index.html                # Main ontology landing page
│   ├── resources/                # Individual resource pages
│   │   ├── SumTemplate.html
│   │   ├── MultiplyTemplate.html
│   │   └── ...
│   └── GITHUB_PAGES_SETUP.md     # This file
├── ontology/
│   └── spw.ttl                   # Main ontology (accessible via Pages)
├── workflows/
│   ├── catalog.ttl               # Workflow definitions (accessible)
│   └── catalog-ui.ttl            # UI metadata (accessible)
└── _config.yml                   # Jekyll configuration
```

## 🎨 Customization

### Add Custom Domain (Optional)

1. In repository Settings → Pages → Custom domain
2. Enter your domain (e.g., `ontology.yoursite.com`)
3. Update namespace URIs to use your custom domain
4. Configure DNS with your domain provider

### Modify Landing Page

Edit `docs/index.html` to customize:
- Styling
- Resource lists
- Documentation links
- Branding

### Add More Resource Pages

Create new files in `docs/resources/` following the pattern in `SumTemplate.html`.

## 🔍 Content Negotiation

The current setup uses client-side JavaScript for content negotiation:

- **HTML request** → Shows documentation page
- **Fragment identifier** → Redirects to resource page
- **`?format=ttl` parameter** → Returns Turtle file

For more advanced server-side content negotiation, consider:
- Using Cloudflare Workers
- Using a custom domain with .htaccess
- Using Netlify redirects

## ✅ Verification Checklist

- [ ] GitHub Pages enabled in repository settings
- [ ] Site accessible at `https://thhanke.github.io/PyodideSemanticWorkflow/`
- [ ] All `.ttl` files updated with new namespace
- [ ] Landing page loads correctly
- [ ] Resource pages accessible
- [ ] RDF files downloadable
- [ ] URIs resolve in RDF tools (rdflib, Apache Jena, etc.)

## 🐛 Troubleshooting

### Site not loading?
- Check if GitHub Pages is enabled in Settings
- Verify the `main` branch and `/docs` folder are selected
- Wait a few minutes for deployment
- Check GitHub Actions tab for build errors

### 404 errors?
- Ensure all HTML files are in the `docs/` directory
- Check that file names match the links
- Verify `_config.yml` includes settings are correct

### URIs not resolving?
- Confirm you've updated all namespace URIs
- Check that `.ttl` files are accessible at their GitHub Pages URLs
- Test with direct file URLs first before fragment identifiers

## 📚 Additional Resources

- [GitHub Pages Documentation](https://docs.github.com/en/pages)
- [Best Practices for Publishing Linked Data](https://www.w3.org/TR/ld-bp/)
- [Cool URIs for the Semantic Web](https://www.w3.org/TR/cooluris/)
- [Content Negotiation Guide](https://www.w3.org/wiki/ContentNegotiation)

## 🔄 Continuous Updates

Every time you push changes to the `main` branch:
1. GitHub automatically rebuilds the Pages site
2. Changes appear within 1-2 minutes
3. URIs remain stable and resolvable

## 📞 Support

For issues or questions:
- Open an issue in the repository
- Check GitHub Pages status: https://www.githubstatus.com/
- Review GitHub Pages documentation
