"""HTML -> PDF rendering for printable procurement documents (WeasyPrint)."""
from django.http import HttpResponse
from django.template.loader import render_to_string


def render_pdf(request, template_name, context, filename, *, download=False):
    """Render a template to a PDF HttpResponse.

    ``download=True`` forces a save dialog; otherwise the PDF opens inline in the
    browser's viewer (from where the user can also save/print).
    """
    from weasyprint import HTML

    html = render_to_string(template_name, context, request=request)
    pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    disposition = "attachment" if download else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return response
