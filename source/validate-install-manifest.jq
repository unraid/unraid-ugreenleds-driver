# Run with -n -e, single-document --slurpfile manifest and approval, and
# --arg unraid/kernel/config_sha256/manifest_sha256/model from the target.
# Emit ordered package name, SHA-256, and size rows only after all checks pass.
def require($condition; $message):
  if $condition then . else error($message) end;
def sha256: type == "string" and test("^[0-9a-f]{64}$");
def safe_name: type == "string" and test("^[A-Za-z0-9_.+-]+$");

require(($manifest | length) == 1 and ($approval | length) == 1;
        "Exactly one candidate and approval document are required")
| $manifest[0] as $m
| $approval[0] as $a
| require(($unraid | test("^7\\.[0-9]+\\.[0-9]+(-(beta|rc)\\.[0-9]+)?$"))
          and ($kernel | test("^[0-9]+\\.[0-9]+\\.[0-9]+-Unraid$"))
          and ($config_sha256 | sha256) and ($manifest_sha256 | sha256)
          and ($model | length) > 0; "Invalid target identity")
| require($m.schema == 1 and $m.recipe == 1 and $m.status == "candidate"
          and $a.schema == 1 and $a.recipe == 1 and $a.status == "approved";
          "Unsupported candidate or approval")
| require($m.unraid == $unraid and $a.unraid == $unraid
          and $m.kernel == $kernel and $a.kernel == $kernel;
          "OS or kernel mismatch")
| require($m.config_sha256 == $config_sha256; "Stock configuration mismatch")
| require($a.manifest_sha256 == $manifest_sha256; "Approval receipt hash mismatch")
| require(($a.system_product_names | type) == "array"
          and ($a.system_product_names | index($model)) != null;
          "This exact hardware model is not approved")
| require(($m.packages | type) == "object"
          and ($m.packages | keys) == ["i2c_tools", "kernel", "monitor"];
          "Incomplete package roles")
| require(($m.assets | type) == "array" and ($m.assets | length) > 0;
          "Missing asset records")
| require(all($m.assets[]; (.name | safe_name) and (.sha256 | sha256)
          and (.size | type) == "number" and .size > 0 and .size == (.size | floor));
          "Invalid asset record")
| require(($m.assets | map(.name) | unique | length) == ($m.assets | length);
          "Duplicate asset names")
| ("unraid-" + $unraid + "-r1--") as $prefix
| require(any($m.assets[]; .name == ($prefix + "stock.config")
          and .sha256 == $config_sha256); "Missing stock configuration evidence")
| [ {role: "i2c_tools", stem: "i2c-tools-"},
    {role: "kernel", stem: "ugreen_leds-"},
    {role: "monitor", stem: "ugreenleds-driver-"} ] as $roles
| require(all($roles[]; . as $role | $m.packages[$role.role] as $name
          | ($name | safe_name) and ($name | startswith($prefix + $role.stem))
          and ($name | endswith(".txz"))
          and any($m.assets[]; .name == $name)); "Invalid package identity")
| $roles[] as $role
| $m.assets[] | select(.name == $m.packages[$role.role])
| [.name, .sha256, (.size | tostring)] | @tsv
