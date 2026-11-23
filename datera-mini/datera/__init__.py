"""DATERA EDU mini."""
# Verify HTTPS with the operating system's certificate store. The python.org build of Python
# on macOS ships without root certificates, so model downloads fail without this.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # the package is optional
    pass
