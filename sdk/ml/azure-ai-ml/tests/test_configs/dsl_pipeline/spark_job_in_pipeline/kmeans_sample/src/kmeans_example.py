"""
An example demonstrating k-means clustering.
This example requires NumPy (http://www.numpy.org/).
"""

import argparse
from pathlib import Path

from pyspark.ml.clustering import KMeans
from pyspark.ml.evaluation import ClusteringEvaluator
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("KMeansExample").getOrCreate()

parser = argparse.ArgumentParser()
parser.add_argument("--file_input")
parser.add_argument("--output")
args = parser.parse_args()

# Loads data.
dataset = spark.read.format("libsvm").load(args.file_input)

# Trains a k-means model.
kmeans = KMeans().setK(2).setSeed(1)
model = kmeans.fit(dataset)

# Make predictions
predictions = model.transform(dataset)

# Evaluate clustering by computing Silhouette score
evaluator = ClusteringEvaluator()

silhouette = evaluator.evaluate(predictions)
print("Silhouette with squared euclidean distance = " + str(silhouette))

# Shows the result.
centers = model.clusterCenters()
print("Cluster Centers: ")
for center in centers:
    print(center)

(Path(args.output) / "result.txt").write_text(str(centers))
