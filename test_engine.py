import fitz

from pdf_engine import find_text_block, insert_text_box, parse_page_ranges, replace_text


def main() -> None:
    assert parse_page_ranges("1,3-4", 5) == [0, 2, 3]
    assert parse_page_ranges("all", 3) == [0, 1, 2]

    document = fitz.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((30, 50), "Original text", fontsize=12)
    block = find_text_block(page, fitz.Point(45, 47))
    assert block is not None
    replace_text(page, block, "Changed text")
    insert_text_box(page, fitz.Rect(30, 90, 220, 140), "A new text box", 12)
    page.draw_line((30, 170), (220, 170))
    page.draw_rect(fitz.Rect(30, 190, 150, 250))
    editable = page.add_circle_annot(fitz.Rect(170, 190, 250, 270))
    editable.set_info(subject="PDFeditEasy Object", content="circle")
    editable.update()
    editable.set_rect(fitz.Rect(180, 200, 280, 300))
    editable.set_rotation(90)
    editable.update()
    text_object = page.add_freetext_annot(
        fitz.Rect(30, 290, 250, 350), "Written by the user", fontsize=13
    )
    text_object.set_info(title="PDFeditEasy", subject="PDFeditEasy Text Object")
    text_object.update()
    text_object.set_info(content="Edited by the user")
    text_object.update()

    pdf_bytes = document.tobytes(garbage=4, deflate=True)
    document.close()
    check = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = check[0].get_text()
    assert "Changed text" in text
    assert "A new text box" in text
    annotations = list(check[0].annots())
    assert len(annotations) == 2
    assert annotations[0].info["content"] == "circle"
    assert annotations[1].info["content"] == "Edited by the user"
    assert "Edited by the user" in text
    check.close()
    print("PDFeditEasy engine smoke test passed")


if __name__ == "__main__":
    main()
