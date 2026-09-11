import yaml

config_data = None

# 读取YAML文件
with open('./config/config.yaml', 'r', encoding='utf-8') as stream:
    try:
        config_data = yaml.safe_load(stream)
        print(config_data)
    except yaml.YAMLError as exc:
        print(exc)



