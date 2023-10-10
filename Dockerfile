# Use an official Python runtime as the parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install Poetry
RUN pip install poetry

# Install project dependencies using Poetry
RUN poetry install

# Explicitly install uvicorn
RUN pip install uvicorn
RUN pip install fastapi
RUN pip install openai
RUN pip install markdown
RUN pip install faiss-gpu
RUN pip install faiss-cpu
RUN pip install toml
RUN pip install tiktoken
RUN pip install numpy
RUN pip install python-multipart
# Make port 80 available to the world outside this container
EXPOSE 80

# Define the command to run the app using Uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]
