# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from core.extract.nextjs_rsc import extract_nextjs_rsc_text


# extract_nextjs_rsc_text — merge split __next_f scripts into structured markdown.

def test_extract_nextjs_rsc_text_handles_split_scripts_and_structure() -> None:
    html = """
    <html>
      <body>
        <script>self.__next_f.push([1,"10:[\\"$\\",\\"$Lheading\\",null,{\\"baseId\\":\\"pricing\\",\\"children\\":\\"Pricing and plans\\"}]\\n11:[\\"$\\",\\"p\\",null,{\\"children\\":\\"Hello wor"])</script>
        <script>self.__next_f.push([1,"ld\\"}]\\n12:[\\"$\\",\\"ul\\",null,{\\"children\\":[[\\"$\\",\\"li\\",null,{\\"children\\":\\"First\\"}],[\\"$\\",\\"li\\",null,{\\"children\\":\\"Second\\"}]]}]\\n13:[\\"$\\",\\"div\\",null,{\\"className\\":\\"full-width-table\\",\\"children\\":[\\"$\\",\\"table\\",null,{\\"children\\":[\\"$\\",\\"tr\\",null,{\\"children\\":[[\\"$\\",\\"td\\",null,{\\"children\\":\\"Auto\\"}],\\"$L14\\"]}]}]}]\\n14:[\\"$\\",\\"td\\",null,{\\"children\\":\\"$$0.25\\"}]\\n"])</script>
      </body>
    </html>
    """

    text = extract_nextjs_rsc_text(html)

    assert "## Pricing and plans" in text
    assert "Hello world" in text
    assert "- First" in text
    assert "- Second" in text
    assert "Auto | $$0.25" in text
