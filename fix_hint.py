import io

path = "gui.py"
with io.open(path, "r", encoding="utf-8") as f:
    content = f.read()

bad = '            skip_hint = "\n（已跳过：" + skip_tag + "）"\n'
good = '            skip_hint = "\\n（已跳过：" + skip_tag + "）"\n'

if bad in content:
    content = content.replace(bad, good)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("FIXED")
else:
    print("PATTERN NOT FOUND")
    i = content.find("skip_hint")
    print(repr(content[i - 40:i + 120]))
