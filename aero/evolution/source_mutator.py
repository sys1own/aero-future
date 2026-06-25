
import os, random, glob
from typing import List, Dict, Any

class SourceMutator:
    def __init__(self, target_files: List[str], rules: List[str], mutation_rate: float = 0.5):
        self.target_files = target_files
        self.rules = rules
        self.mutation_rate = mutation_rate
        self._backups = {}

    def mutate(self, workspace: str) -> Dict[str, Any]:
        mutated_files = []
        for pattern in self.target_files:
            full_pattern = os.path.join(workspace, pattern)
            files = glob.glob(full_pattern, recursive=True)
            for fpath in files:
                if random.random() < self.mutation_rate:
                    try:
                        with open(fpath, 'r') as f:
                            source = f.read()
                        self._backups[fpath] = source
                        rule = random.choice(self.rules)
                        if rule == "insert_function_stub":
                            if "# Aero Future Mutation" not in source:
                                stub = "\n# Aero Future Mutation\ndef aero_future_function(data):\n    print('Evolved function called!')\n    return data\n"
                                new_source = source.rstrip() + "\n" + stub
                                with open(fpath, 'w') as f:
                                    f.write(new_source)
                                mutated_files.append(fpath)
                        elif rule == "add_docstring":
                            if "Aero Future Docstring" not in source:
                                lines = source.splitlines()
                                new_lines = []
                                in_function = False
                                for i, line in enumerate(lines):
                                    new_lines.append(line)
                                    if not in_function and line.strip().startswith("def "):
                                        in_function = True
                                        if ":" in line:
                                            indent = len(line) - len(line.lstrip())
                                            next_line = lines[i+1] if i+1 < len(lines) else ""
                                            if not next_line.strip().startswith('"') and not next_line.strip().startswith("'"):
                                                new_lines.append(" " * (indent + 4) + '"""Aero Future Docstring."""')
                                                break
                                if in_function:
                                    with open(fpath, 'w') as f:
                                        f.write("\n".join(new_lines))
                                    mutated_files.append(fpath)
                    except Exception as e:
                        print(f"Error mutating {fpath}: {e}")
        return {"mutated_files": mutated_files}

    def rollback(self):
        for fpath, content in self._backups.items():
            with open(fpath, 'w') as f:
                f.write(content)
        self._backups.clear()
