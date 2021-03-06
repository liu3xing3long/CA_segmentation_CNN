from __future__ import print_function

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.ioff()

import os
from keras import backend as K
from os.path import join, basename
from os import makedirs
import csv
import SimpleITK as sitk
from tqdm import tqdm
import numpy as np
import pandas as pd
import scipy.ndimage.morphology
from skimage import measure, filters
from preprossesing import *
from loss_function import dice_coefficient
from metric import recall, precision

from keras import backend as K
K.set_image_data_format('channels_last')
#from keras.utils import print_summary
import scipy.ndimage as nd
from skimage import measure


def refine_binary(im, k=None):
    if k is None:
        k = np.ones((1, 1, 1))
    #print('Loading image %s' % os.path.split(im_fp)[-1])
    #im = nib.load(im_fp).get_data()
    print(np.unique(im))
    print('Creating binary closing of image...')
    im_closed = (im > 0).astype(np.float32)
    #im_closed = nd.morphology.grey_closing(im_closed, structure=k).astype(np.float32)
    print('Running connected components on closed image...')
    cc_closed = measure.label(im_closed, background=0)
    del im_closed
    lbls, counts = np.unique(cc_closed, return_counts=True)
    print(lbls, counts)
    branches = np.argsort(counts)[-3:-1]
    print(np.argsort(counts))
    print(branches)
    print('Pruning closed image...')
    im_closed_ref = (cc_closed == branches[0]).astype(np.float32)
    im_closed_ref[np.where(cc_closed==branches[1])] = 1.0
    print('Running CC on non-binary image...')
    cc = measure.label(im, background=0)
    lbls = np.unique(cc[np.where(im_closed_ref>0)])
    lbls = np.delete(lbls, np.where(lbls==0)) # Remove background label
    del im_closed_ref
    print('Creating final refined segmentation...')
    im_refined = np.isin(cc, lbls).astype(np.float32)
    if np.array_equal(im, im_refined):
        print("No refinement")
    return im_refined

def simple_refine(im):
    # Label connected components
    cc, num_cc = nd.label(im)
    # Find counts of unique elements in the cc volume
    unique, counts = np.unique(cc, return_counts=True)
    # Sort counts (ascending order), return indices and reverse it
    print(counts)
    counts_sorted = np.argsort(counts)
    print(counts_sorted)

    # Largest count is always background
    #bg_lbl = counts_sorted[-1]
    # Assume that the two largest connected components are the coronary branches
    b1_lbl = counts_sorted[1]
    #b2_lbl = counts_sorted[-3]

    refined_im = np.zeros(im.shape, dtype=np.float32)
    refined_im[np.where(cc==b1_lbl)] = 1.0
    refined_im[np.where(cc==b2_lbl)] = 1.0

    return refined_im


def threshold_mask(raw_output, threshold):
    if threshold == 0:
        try:
            threshold = filters.threshold_otsu(raw_output)
        except:
            threshold = 0.5

    print('\tThreshold: {}'.format(threshold))

    raw_output[raw_output > threshold] = 1
    raw_output[raw_output < 1] = 0
    im_closed = nd.morphology.grey_closing(raw_output, structure=np.ones((3, 3, 3))).astype(np.float32)

    all_labels = measure.label(raw_output)
    props = measure.regionprops(all_labels, coordinates='rc')
    props.sort(key=lambda x: x.area, reverse=True)
    thresholded_mask = np.zeros(raw_output.shape)
    for prop in props:
        if prop.area > 500:
            thresholded_mask[all_labels == prop.label] = 1
    """if len(props) >= 2:
        if props[0].area / props[1].area > 5:  # if the largest is way larger than the second largest
            thresholded_mask[all_labels == props[0].label] = 1  # only turn on the largest component
        else:
            thresholded_mask[all_labels == props[0].label] = 1  # turn on two largest components
            thresholded_mask[all_labels == props[1].label] = 1
    elif len(props):
        thresholded_mask[all_labels == props[0].label] = 1

    #thresholded_mask = scipy.ndimage.morphology.binary_fill_holes(thresholded_mask).astype(np.uint8)

    return thresholded_mask"""
    return thresholded_mask

def make_result_csvfile(output_dir, test_list, outfile='', compute_dice=1, compute_recall=1, compute_precision=1):
    # Set up placeholders
    with open(join(output_dir, outfile + 'scores.csv'), 'wb') as csvfile:
        writer = csv.writer(csvfile, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
        print("open writer")
        row = ['Scan Name']
        if compute_dice:
            row.append('Dice Coefficient')
        if compute_recall:
            row.append('Recall')
        if compute_precision:
            row.append('precision')


        writer.writerow(row)

def add_result_to_csvfile(img_name, prediction, gt_data, output_dir, outfile, compute_dice=1, compute_recall=1, compute_precision=1):
    with open(join(output_dir,  outfile + 'scores.csv'), 'ab+') as csvfile:
        writer = csv.writer(csvfile, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
        row = img_name
        prediction = prediction.reshape(gt_data.shape)
        if compute_dice:
            print('Computing Dice')
            dice_arr = K.eval(dice_coefficient(prediction.astype(np.float32), gt_data.astype(np.float32)))
            print('\tDice: {}'.format(dice_arr))
            row.append(dice_arr)

        if compute_recall:
            print('Computing Recall')
            recall_arr = K.eval(recall(prediction.astype(np.float32), gt_data.astype(np.float32)))
            print('\tRecall: {}'.format(recall_arr))
            row.append(recall_arr)

        if compute_precision:
            print('Computing Precision')
            precision_arr = K.eval(precision(prediction.astype(np.float32), gt_data.astype(np.float32)))
            print('\tPrecision: {}'.format(precision_arr))
            row.append(precision_arr)

        writer.writerow(row)

def compute_avg(output_dir, outfile, compute_dice=1, compute_recall=1, compute_precision=1):
    result = np.float32(pd.read_csv(join(output_dir,  outfile + 'scores.csv'), sep=',',header=None).values[1:,1:])
    row = ['Average Scores']
    with open(join(output_dir,  outfile + 'scores.csv'), 'ab+') as csvfile:
        writer = csv.writer(csvfile, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
        if compute_dice:
            row.append(np.mean(result[:,0]))
        if compute_recall:
            row.append(np.mean(result[:,1]))
        if compute_precision:
            row.append(np.mean(result[:,2]))
        writer.writerow(row)



def plot_gt_predtion_on_slices(img_data, output_bin, gt_data, path):
    print('Creating Qualitative Figure for Quick Reference')
    f, ax = plt.subplots(1, 3, figsize=(15, 5))

    ax[0].imshow(img_data[img_data.shape[0] // 3, :, :], alpha=1, cmap='gray')
    ax[0].imshow(output_bin[img_data.shape[0] // 3, :, :], alpha=0.5, cmap='Blues')
    ax[0].imshow(gt_data[img_data.shape[0] // 3, :, :], alpha=0.2, cmap='Reds')
    ax[0].set_title('Slice {}/{}'.format(img_data.shape[0] // 3, img_data.shape[0]))
    ax[0].axis('off')

    ax[1].imshow(img_data[img_data.shape[0] // 2, :, :], alpha=1, cmap='gray')
    ax[1].imshow(output_bin[img_data.shape[0] // 2, :, :], alpha=0.5, cmap='Blues')
    ax[1].imshow(gt_data[img_data.shape[0] // 2, :, :], alpha=0.2, cmap='Reds')
    ax[1].set_title('Slice {}/{}'.format(img_data.shape[0] // 2, img_data.shape[0]))
    ax[1].axis('off')

    ax[2].imshow(img_data[img_data.shape[0] // 2 + img_data.shape[0] // 4, :, :], alpha=1, cmap='gray')
    ax[2].imshow(output_bin[img_data.shape[0] // 2 + img_data.shape[0] // 4, :, :], alpha=0.5,
                 cmap='Blues')
    ax[2].imshow(gt_data[img_data.shape[0] // 2 + img_data.shape[0] // 4, :, :], alpha=0.2,
                 cmap='Reds')
    ax[2].set_title(
        'Slice {}/{}'.format(img_data.shape[0] // 2 + img_data.shape[0] // 4, img_data.shape[0]))
    ax[2].axis('off')

    fig = plt.gcf()
    fig.suptitle(path)

    plt.savefig(path, format='png', bbox_inches='tight')
    plt.close('all')


def create_and_write_viz_nii(name, meta_sitk, pred, gt):
    print(np.unique(pred))
    pred[pred > 0.] = 2.
    print(np.unique(pred))
    print(np.unique(gt))
    vis_image = gt + pred
    print(np.unique(vis_image))
    viz_sitk = sitk.GetImageFromArray(vis_image)
    viz_sitk.CopyInformation(meta_sitk)
    sitk.WriteImage(viz_sitk, name)



def test(args, test_list, label, model, modelpath):
    print("Inside test")
    """if args.weights_path == '':
        weights_path = join(args.check_dir, args.output_name + '_model_' + args.time + '.hdf5')
    else:
        weights_path = join(args.data_root_dir, args.weights_path)"""

    output_dir = join('results', basename(modelpath.replace(".hdf5", "")))
    raw_out_dir = join(output_dir, 'raw_output')
    fin_out_dir = join(output_dir, 'final_output')
    fig_out_dir = join(output_dir, 'qual_figs')
    try:
        makedirs(raw_out_dir)
    except:
        pass
    try:
        makedirs(fin_out_dir)
    except:
        pass
    try:
        makedirs(fig_out_dir)
    except:
        pass

    make_result_csvfile(output_dir, test_list, outfile='raw_')
    make_result_csvfile(output_dir, test_list, outfile='post_')

    for i, img in enumerate(tqdm(test_list)):
        sitk_img = sitk.ReadImage(test_list[i][0])
        img_data = sitk.GetArrayFromImage(sitk_img)
        num_slices = img_data.shape[0]
        if "3D" in modelpath:
            pred_sample, pred_label, orgshape = get_prediced_patches_of_test_file(test_list, i, "both")
            pred_output = model.predict(pred_sample,  batch_size=1, verbose=1)
            output = from_patches_to_numpy(pred_output, orgshape)
            output= output[:num_slices]
            output_array = output.reshape(img_data.shape)

        else:
            #pred_sample, pred_label = get_prediced_image_of_test_files(args, test_list, i, tag=label)
            numpy_image, numpy_label = get_preprossed_numpy_arrays_from_file(img[0], img[1])
            pred_sample, mask = add_neighbour_slides_training_data(numpy_image, numpy_label, args.stride, args.channels)
            print("gathered pred_sample")
            output_array = model.predict(pred_sample,  batch_size=1, verbose=1)

            output = output_array[:,:,:,0]

        output_rawimg = sitk.GetImageFromArray(output)
        print('Segmenting Output')
        output_bin = threshold_mask(output, 0.0)
        #output_bin = simple_refine(output)
        output_mask = sitk.GetImageFromArray(output_bin)

        output_rawimg.CopyInformation(sitk_img)
        output_mask.CopyInformation(sitk_img)

        print('Saving Output')
        sitk.WriteImage(output_rawimg, join(raw_out_dir, img[0].split("/")[-1][:-7] + '_raw_output' + img[0][-7:]))
        sitk.WriteImage(output_mask, join(fin_out_dir, img[0].split("/")[-1][:-7] + '_final_output' + img[0][-7:]))
        sitk_mask = sitk.ReadImage(img[1])
        gt_data = sitk.GetArrayFromImage(sitk_mask).astype(np.float32)

        add_result_to_csvfile([img[0][:-7]], output_array, gt_data, output_dir, outfile='raw_')
        add_result_to_csvfile([img[0][:-7]], output_bin, gt_data, output_dir, outfile='post_')
        create_and_write_viz_nii(join(raw_out_dir, img[0].split("/")[-1][:-7] + '_viz_' + img[0][-7:]), sitk_img, output, gt_data)
        # Plot Qual Figure
        #plot_gt_predtion_on_slices(img_data, output_array, gt_data, join(fig_out_dir, img[0].split("/")[-1][:-7] + '_qual_fig' + '.png'))"""
    compute_avg(output_dir, 'raw_', compute_dice=1, compute_recall=0, compute_precision=0)
    compute_avg(output_dir, 'post_', compute_dice=1, compute_recall=0, compute_precision=0)
    print('Done.')



if __name__=="__main__":
    writer = make_result_csvfile(True, join('results', ""), ["hei", "yo"])
