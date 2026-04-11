import jinja2
import os

def check_template(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    try:
        jinja2.Template(content)
        print(f"OK: {filepath}")
    except Exception as e:
        print(f"ERROR: {filepath}: {e}")

templates_dir = r'c:\Users\DeLL\OneDrive\Documents\School\templates'
for root, dirs, files in os.walk(templates_dir):
    for file in files:
        if file.endswith('.html'):
            check_template(os.path.join(root, file))
