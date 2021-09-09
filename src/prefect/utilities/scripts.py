import os
from typing import Any, Dict


def exec_script(
    file_path: str,
) -> Dict[str, Any]:
    """
    Execute a python script with __file__ populated if feasible and return the global
    variables
    """
    with open(file_path, "r") as f:
        file_contents = f.read()

    # If a file_path has been provided, provide __file__ as a global variable
    # so it resolves correctly during extraction
    exec_vals: Dict[str, Any] = {
        "__file__": file_path,
        "__name__": os.path.dirname(file_path),
    }

    # Compile the code so the file is attached to any traceback frames that arise
    # This allows tracebacks to reference failing lines nicely
    code = compile(
        file_contents,
        filename=os.path.abspath(file_path),
        mode="exec",
    )

    exec(code, exec_vals)

    # Globals from the script will be populated in this dict now
    return exec_vals
