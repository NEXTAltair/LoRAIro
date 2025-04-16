"""image_annotator_lib 現在使えるモデルめいを表示"""

from image_annotator_lib import list_available_annotators

annotators = list_available_annotators()

for annotator in annotators:
    print(annotator)
