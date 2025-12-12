# Font Loading Issue Research Notes

## Problem Description

When archiving websites from the Wayback Machine, fonts may not load correctly in the local copy, even though they appear to work correctly when viewing the same page directly on the Wayback Machine website.

## Observed Symptoms

1. **Typography appears different** - Fonts render with fallback fonts (e.g., Arial, Times) instead of the intended custom fonts (e.g., Montserrat)
2. **Font files are missing** - No font files (`.woff`, `.woff2`, `.ttf`, `.eot`, `.svg`) are found in the downloaded archive
3. **CSS references external fonts** - The HTML contains links to external font services like `fonts.googleapis.com`
4. **Font files are corrupted** - Some font files downloaded from Wayback Machine are actually HTML error pages instead of font files

## Technical Analysis

### External Font Services

Many websites use external font services (Google Fonts, Adobe Fonts, etc.) that are loaded via:
- `<link href="http://fonts.googleapis.com/css?family=Montserrat" rel="stylesheet">`
- `@import url('https://fonts.googleapis.com/css?family=Montserrat');`

**Issue**: The Wayback-Archive scraper is configured to only download internal resources (same domain). External font services are not downloaded, so fonts fail to load locally.

**Current Behavior**: 
- External font CSS links are preserved in HTML but point to external URLs
- When viewing locally, browsers try to load fonts from external services
- If offline or if external services are blocked, fonts fall back to system defaults

### Corrupted Font Files from Wayback Machine

Some font files downloaded from Wayback Machine return HTML error pages instead of actual font files. This is especially common with:
- `.eot` (Embedded OpenType) files - older IE format, often not preserved well
- `.svg` (SVG fonts) - deprecated format, often returns error pages

**Current Solution**: 
- The scraper detects corrupted fonts by checking if downloaded content is HTML instead of a font file
- Corrupted font references are automatically removed from CSS
- This prevents browsers from trying to load HTML error pages as fonts

### Font Format Priority in CSS

Modern CSS `@font-face` declarations often include multiple font formats:
```css
@font-face {
  font-family: 'Montserrat';
  src: url('montserrat.eot'); /* IE9 Compat Modes */
  src: url('montserrat.eot?#iefix') format('embedded-opentype'),
       url('montserrat.woff2') format('woff2'),
       url('montserrat.woff') format('woff'),
       url('montserrat.ttf') format('truetype');
}
```

**Issue**: If the first format (`.eot`) is corrupted and removed, but the browser doesn't support the remaining formats, fonts may not load.

## Potential Solutions to Research

1. **Download External Font Services**: 
   - Modify the scraper to download Google Fonts CSS and all referenced font files
   - Parse Google Fonts CSS to extract actual font file URLs
   - Download and rewrite font URLs to local paths

2. **Font Substitution**:
   - Detect when fonts fail to load
   - Automatically substitute with similar system fonts
   - Or download fonts from alternative sources (e.g., Google Fonts API)

3. **Font Format Conversion**:
   - Convert corrupted or missing font formats to working formats
   - Use tools like `woff2` or `fonttools` to convert between formats

4. **Better Font Detection**:
   - Improve detection of corrupted fonts beyond just checking for HTML
   - Validate font file headers (magic numbers) to ensure they're actual fonts
   - Check font file integrity before removing from CSS

5. **Font Loading Fallback**:
   - Keep external font links but add local fallbacks
   - Use CSS `font-display: swap` to show content immediately with fallback fonts
   - Load fonts asynchronously and swap when available

## Questions for Research

1. How does Wayback Machine handle external font services? Does it proxy them or leave them as external links?
2. Can we programmatically download fonts from Google Fonts API using the same parameters as the original site?
3. Are there legal/licensing issues with downloading and redistributing fonts from external services?
4. What's the best way to detect and handle font format compatibility across different browsers?
5. Should the scraper have an option to download external fonts, or should it remain internal-only by default?

## Current Implementation Status

- ✅ Corrupted font detection (HTML error pages)
- ✅ Automatic removal of corrupted font references from CSS
- ✅ Removal of `.eot` and `.svg` font formats (often corrupted)
- ❌ External font service downloading (not implemented)
- ❌ Font format conversion (not implemented)
- ❌ Font substitution/fallback (not implemented)

