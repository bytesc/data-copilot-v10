
from .path_tools import generate_img_path


def get_ask_graph_prompt(question,col_explanation=None, tmp_file=False):
    pre_prompt = """
Please use matplotlib to draw a graph based on the question. 
No calculation in this step, just draw graph with given data
The Python function should return a string of file path in `./tmp_imgs/` only 
and the image generated should be stored in that path. 
file path must be:
"""
    example_code = """
Here is an example: 
```python
def func(data):
    import pandas as pd
    import math
    import numpy as np
    import PIL
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.family'] = 'SimHei' 
    # please keep the code above!
    # generate code to perform operations here
    return path
```

Remind:
- Pay attention to the scale division of the horizontal axis and the orientation of the text to avoid excessive density of the horizontal axis and overlapping text!!!
"""
    col_prompt = ""
    if col_explanation:
        col_prompt = "\ndf columns explanation: "+str(col_explanation)+"\n"
    if not tmp_file:
        return pre_prompt + "`"+generate_img_path()+"`"+example_code+col_prompt+"question:"+question
    else:
        return pre_prompt + "./tmp_imgs/tmp.png" + example_code+col_prompt+"question:"+question


def get_ask_compare_graph_prompt(question, col_explanation=None, tmp_file=False):
    pre_prompt = """
Please use matplotlib to draw a graph based on the question. 
No calculation in this step, just draw graph with given data
The Python function should return a string of file path in `./tmp_imgs/` only 
and the image generated should be stored in that path. 
file path must be:
"""
    example_code = """
Here is an example: 
```python
def func(data_dict):
    import pandas as pd
    import math
    import numpy as np
    import PIL
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.family'] = 'SimHei'
    # please keep the code above!
    # generate code to perform operations here
    
    return path
```

Remind:
- Pay attention to the scale division of the horizontal axis and the orientation of the text to avoid excessive density of the horizontal axis and overlapping text!!!
- You should overlay different layers of different color bar charts or line graphs when comparing something.
"""
    col_prompt = ""
    if col_explanation:
        col_prompt = "\ndf columns explanation: "+str(col_explanation)+"\n"
    if not tmp_file:
        return pre_prompt + "`"+generate_img_path()+"`"+example_code+col_prompt+"question:"+question
    else:
        return pre_prompt + "./tmp_imgs/tmp.png" + example_code+col_prompt+"question:"+question


