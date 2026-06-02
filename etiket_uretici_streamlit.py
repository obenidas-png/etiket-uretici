"""Streamlit entry point for GitHub/Render deployments.

The application code lives in the modular `app.py` file. This wrapper keeps
older deployments that run `streamlit run etiket_uretici_streamlit.py` working.
"""

from app import main


if __name__ == "__main__":
    main()
