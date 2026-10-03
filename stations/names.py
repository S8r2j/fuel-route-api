"""
Compare place names written differently in different sources
"""
import unicodedata

def name_key(name):
    """
    Return the name reduced to lowercase ASCII letters and digits.

    This makes spelling differences between the two files irrelevant:
        "MC Calla", "McCalla"   -> "mccalla"
        "O'Neill", "Oneill"     -> "oneill"
    """
    text = unicodedata.normalize("NFKD", name.lower()) # normalize("NFKD",...) splits an accented letter into plain letter
    return "".join(char for char in text if char.isascii() and char.isalnum())
