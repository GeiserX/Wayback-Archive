# Security Policy

## Reporting a vulnerability

Do not report security vulnerabilities through public GitHub issues. Use
GitHub's private vulnerability reporting instead:

1. Go to the **Security** tab of this repository.
2. Click **Report a vulnerability**.
3. Describe the issue, the version, and the steps or the archived page that triggers it.

You get a first answer within a week. A confirmed issue is fixed in a new
release, and the advisory is published once that release is on PyPI.

## Supported versions

Only the latest minor release gets security fixes. Today that is 1.5.x; every
1.4.x version can be made to fetch arbitrary hosts, so upgrade.

## What counts as a security issue

The tool downloads pages written by strangers and follows the links in them,
so the archived content is untrusted input. These are vulnerabilities:

- A request to any host other than `web.archive.org` and the fixed list of
  CDNs the tool fetches live (Google Fonts, `code.jquery.com`, the Squarespace
  CDN), for example through a crafted URL in an archived page.
- A file written, overwritten or deleted outside `OUTPUT_DIR`, for example
  through `..` or an absolute path in an archived URL.
- Code from an archived page running on the machine that runs the tool.

A script in an archived page that runs in your browser when you open the
offline copy is not one of them: the copy reproduces the site as it was.
Open copies of sites you do not trust with care.
