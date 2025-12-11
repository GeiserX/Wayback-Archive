# HTTP Server Troubleshooting Guide

## Common Issue: Port Already in Use

If you see "nothing being served" or connection errors, the most common cause is **multiple Python processes trying to use the same port**.

### Solution: Use a Different Port

Instead of port 8000, try port 8080 or another available port:

```powershell
cd "C:\Users\Sergio\Documents\GitHub\clvreformas"
python -m http.server 8080
```

Then access at: `http://localhost:8080/`

### Check What's Using Port 8000

```powershell
netstat -ano | findstr :8000
```

### Kill All Processes on a Port

```powershell
# Kill all processes on port 8000
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { 
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue 
}
```

### Kill All Python Processes

```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
```

## Verify Server is Working

```powershell
# Test if server is responding
Invoke-WebRequest -Uri "http://localhost:8080/" -UseBasicParsing
```

## Why This Happens

When running commands in the background, if the process isn't properly terminated, it can leave orphaned processes listening on the port. Using a different port avoids conflicts entirely.

