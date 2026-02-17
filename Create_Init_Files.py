import os

for root, dirs, files in os.walk("."):
    if "__init__.py" not in files:
        open(os.path.join(root, "__init__.py"), "a").close()