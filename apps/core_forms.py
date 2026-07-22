def aplicar_select2(form, campos, placeholder="Pesquise ou selecione", ajax_urls=None):
    ajax_urls = ajax_urls or {}
    for campo in campos:
        if campo not in form.fields:
            continue
        widget = form.fields[campo].widget
        classes = widget.attrs.get("class", "").split()
        if "select2-field" not in classes:
            classes.append("select2-field")
        widget.attrs["class"] = " ".join(classes).strip()
        widget.attrs.setdefault("data-placeholder", placeholder)
        if campo in ajax_urls:
            widget.attrs["data-ajax-url"] = ajax_urls[campo]
