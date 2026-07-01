# 数据分析沙箱镜像 —— 强隔离执行 LLM 生成的 Python
# 预装数据科学库；与宿主文件系统/网络隔离
FROM python:3.11-slim

# 禁用 pip 缓存减小体积
RUN pip install --no-cache-dir \
    pandas==2.2.3 \
    numpy==1.26.4 \
    scipy==1.13.1 \
    scikit-learn==1.5.2 \
    matplotlib==3.9.2 \
    plotly==5.24.1 \
    kaleido==0.2.1 \
    pyarrow==15.0.2

# 非 root 运行
RUN useradd -m sandbox
USER sandbox
WORKDIR /tmp

# 默认命令由 docker run 传入
CMD ["python", "-c", "print('sandbox ready')"]
