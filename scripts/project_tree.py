import os

def list_files(startpath, exclude_dirs=None):
    if exclude_dirs is None:
        exclude_dirs = {'.git', 'venv', '__pycache__', '.pytest_cache', 'staticfiles', 'static'}
    
    for root, dirs, files in os.walk(startpath):
        # Filter directories in-place to prevent os.walk from descending into them
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f'{indent}{os.path.basename(root)}/')
        sub_indent = ' ' * 4 * (level + 1)
        for f in files:
            print(f'{sub_indent}{f}')

if __name__ == "__main__":
    project_path = r"d:\ANTIGRAVITY_FIN\INADIMPLENTES"
    list_files(project_path)
