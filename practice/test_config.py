from pathlib import Path

from core.models_public import SandboxConfig

config = SandboxConfig.model_validate_json(Path("sandbox_template.json").read_text())
print("From the JSON file:")
print(config)

print("\nDefault values (without a file):")
print(SandboxConfig())