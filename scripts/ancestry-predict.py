from pathlib import Path
import sys
import time


def read_somalier(path):
    """
    take a path to a single .somalier file and return a simple datastructure
    containing the sample information
    """
    data = Path(path).read_bytes()
    version = int.from_bytes(data[:1], byteorder="little")
    assert version == 2
    data = data[1:]
    sample_L = int.from_bytes(data[:1], byteorder="little")
    data = data[1:]
    sample = data[:sample_L].decode()
    data = data[sample_L:]

    nsites = int.from_bytes(data[:2], byteorder="little")
    data = data[2:]
    nxsites = int.from_bytes(data[:2], byteorder="little")
    data = data[2:]
    nysites = int.from_bytes(data[:2], byteorder="little")
    data = data[2:]

    sites = np.frombuffer(data[:nsites * 3 * 4], dtype=np.uint32).reshape((nsites, 3))
    data = data[nsites * 3 * 4:]
    x_sites = np.frombuffer(data[:nxsites * 3 * 4], dtype=np.uint32).reshape((nxsites, 3))
    data = data[nxsites * 3 * 4:]
    y_sites = np.frombuffer(data[:nysites * 3 * 4], dtype=np.uint32).reshape((nysites, 3))

    return dict(sample=sample, sites=sites, x_sites=x_sites)

if __name__ == "__main__":

    from sklearn.decomposition import PCA
    import seaborn as sns
    from sklearn import svm
    from sklearn.metrics import confusion_matrix, accuracy_score
    from sklearn.pipeline import make_pipeline
    import numpy as np
    import pandas as pd
    from matplotlib import pyplot as plt
    import argparse

    sns.set_palette(sns.color_palette("Set1", 12))
    colors = sns.color_palette()

    p = argparse.ArgumentParser("predict ancestry given a labelled background set")
    p.add_argument("--labels", required=True, help="tsv file of sample => ancestry for background set first column must be sample-id")
    p.add_argument("--label-column", help="column name with population label from --labels", default="superpop")
    p.add_argument("--backgrounds", nargs="+", help="path to background *.somalier files matching those specified in labels")
    p.add_argument("--samples", nargs="+", help="path to sample *.somalier for ancestry prediction")

    args = p.parse_args()

    label = args.label_column

    bg_samples = []
    bg_ABs = []
    test_samples = []
    test_ABs = []
    for f in args.backgrounds:
        s = read_somalier(f)
        depth = s["sites"].sum(axis=1)
        ab = s["sites"][:, 0] / np.maximum(depth, 1).astype(float)
        ab[depth < 5] = -1
        bg_ABs.append(ab)
        bg_samples.append(s["sample"])

    for f in args.samples:
        s = read_somalier(f)
        depth = s["sites"].sum(axis=1)
        ab = s["sites"][:, 0] / np.maximum(depth, 1).astype(float)
        ab[depth < 5] = -1
        test_ABs.append(ab)
        test_samples.append(s["sample"])

    bg_sample_df = pd.read_csv(args.labels, sep="\t", escapechar='#', index_col=0)

    clf = make_pipeline(PCA(n_components=5, whiten=True, copy=True, svd_solver="randomized"),
                svm.SVC(C=3, probability=True, gamma="auto"))


    # convert labels to integers
    bg_samples = np.array(bg_samples)
    test_samples = np.array(test_samples)
    bg_ABs = np.array(bg_ABs, dtype=float)
    test_ABs = np.array(test_ABs, dtype=float)

    unk = (bg_ABs == -1).sum(axis=0)
    rm = unk / float(len(bg_samples)) > 0.2
    if len(test_ABs) > 0:
        unk |= (test_ABs == -1).sum(axis=0)
        rm |=  (unk / float(len(test_samples)) > 0.5)

    bg_ABs = bg_ABs[:, ~rm]
    if len(test_ABs) > 0:
        test_ABs = test_ABs[:, ~rm]

    bg_sample_df = bg_sample_df.loc[bg_samples, :]
    targetL = list(bg_sample_df[label].unique())


    target = np.array([targetL.index(p) for p in bg_sample_df[label]])

    clf.fit(bg_ABs, target)

    bg_reduced = clf.named_steps["pca"].transform(bg_ABs)
    if len(test_ABs) > 0:
        test_reduced = clf.named_steps["pca"].transform(test_ABs)
        test_pred = clf.predict(test_ABs)
        test_prob = clf.predict_proba(test_ABs)
        np.set_printoptions(formatter={'float_kind':lambda x: "%.2f" % x})


    print("#sample\t" + "\t".join(targetL))
    for i, sample in enumerate(test_samples):
        print(sample + "\t" + "\t".join("%.2f" % x for x in test_prob[i, :]))

    fig, axes = plt.subplots(1) #, len(targetL) + 1, figsize=(22, 12))
    axes = (axes,)
    for i, l in enumerate(sorted(set(bg_sample_df[label]))):
        sel = bg_sample_df[label] == l
        ibg_sample_df = bg_sample_df.loc[sel, :]
        axes[0].scatter(bg_reduced[sel, 0], bg_reduced[sel, 1], label=l, s=8,
                alpha=0.15, c=[colors[i % len(colors)]], ec='none')

        if len(test_ABs) > 0:
            test_sel = (test_pred == targetL.index(l))
            axes[0].scatter(test_reduced[test_sel, 0], test_reduced[test_sel, 1], s=4,
                alpha=0.9, c=[colors[i % len(colors)]])

    #for ax in axes: ax.legend()
    plt.legend()
    plt.tight_layout()
    plt.show()
