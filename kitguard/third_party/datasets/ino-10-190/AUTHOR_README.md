# Industrial object detection using sim2real domain randomization for robotic applications

This repository contains the followings:
* Implementation of our sim2real object detection framework with
  * The Data data generator module
  * The Training module
  * The Evaluation module
* Manually annotated test dataset of 190 images from 920 objects (of 10 classes)
* Our results

## Requirements

The code was developed on Ubuntu 18.04 and later on Ubuntu 20.04 operating systems, using python3 in a conda environment. The YML file containing the conda environment is available at `cfg/simenv.yml`.

Conda installation: [link](https://docs.conda.io/projects/conda/en/latest/user-guide/install/linux.html)

Git LFS: [link](https://git-lfs.github.com/)  (It is important to install Git LFS properly, otherwise some essential files will not be pulled from the git repository)

## Installation

For installation the followings steps must be done from the base directory:

1. Clone the repository:
```sh
git clone --recurse-submodules git@git.sztaki.hu:emi/sim2real-object-detection.git
```

2. Go into the base directory of the repository:
```sh
cd sim2real-object-detection/
```

3. If you did not clone recursively (`--recurse-submodules`), init the submodule (https://github.com/AlexeyAB) as:
```sh
git submodule update --init
```

4. Initialize your conda environment [link](https://conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#creating-an-environment-from-an-environment-yml-file):
```sh
conda env create -f cfg/simenv.yml
conda activate simenv
```
Alternatively, you can install the packages manually (check `cfg/simenv.yml`)

5. Run python init.py:
```sh
python3 init.py
```
It creates some folders, installs some python libraries and does some additional, minor changes. Feel free to check the script before running.

6. Set up the build file of darknet:
```sh
nano training/yolo/darknet/build/Makefile
```
and set the following variables:
```sh
GPU=1
CUDNN=1
CUDNN_HALF=1
OPENCV=1
```
  If you do not have GPU / CUDNN / OPENCV, you should set them to 0. Nevertheless, you will need at least one GPU for the training. Do not forget to save the file.

  If you do not have opencv installed, you will not be able to use mosaic data augmentation tool at training. For this reason set `mosaic=0` in the 26th row of the `training/yolo/cfg/yolov4-hd-10class.cfg` file.

7. Build darknet:
```sh
cd training/yolo/darknet
make -f build/Makefile
```

8. Check if it Darknet was built properly:
```sh
./darknet
```
You should get this:
```sh
usage: ./darknet <function>
```


## Usage

### Data generation

The code for data generation can be found in the `training/data_generator` folder. You can generate synthetic images by running the `main_generate.py` file. Two arguments are needed:
* the name of the created dataset
* the number of the training sessions you will use

As an example:
```sh
python3 main_generate.py name_of_your_dataset 3
```
It is important that you cannot set more training sessions than the number of GPUs. If you only have one GPU, set it to 1. You should also set the `gpu_nums` parameter to define which GPU-s you wish to train the models on.

If you want to change the data generating method, you must change the parameters in `main_generate.py`. The output directory of your dataset, is the `training/training_datasets/saved` folder.

### Training

The code for training the YOLOv4 CNN can be found in the `training/yolo/code` folder. You can start a training by running the `main_train.py` file. Two arguments are needed:
* the name of the created dataset
* the number of training sessions

As an example:
```sh
python3 main_train.py name_of_your_dataset 3
```
After the training is done, you have to assess the model on the training, on the validation, and on the test set as well, to do so you must run the `main_get_results.py` from the same directory with the same parameters:

As an example:
```sh
python3 main_get_results.py name_of_your_dataset 3
```

It is important that the dataset with the proper name must exist in the `training/training_datasets/saved` folder. The training sessions are executed on different GPU-s concurrently. The results will be saved to the `training/yolo/results` folder.

### Evaluation

The code for evaluating the results is in the `results/code` folder. You can process and plot the results of the training by running these scripts:
```sh
python3 main_process.py name_of_your_dataset 3
python3 main_plot.py name_of_your_dataset 3
```
The arguments as always:
* the name of the created dataset
* the number of training sessions

It is important that results with the proper name must exist in the `training/yolo/results` folder. The processing script only creates text files about the results. The plotting script reads these text files and plotting different graphs. The text files and plots are generated into the `results/results` folder.

### All-in-one pipeline

If you do not want to start the data generation, the training, and the evaluation process separately, you can run the `main.py` script (base directory) with the usual arguments:  
* the name of the created test_dataset
* the number of training sessions
```sh
python3 main.py name_of_your_dataset 3
```

### Execution in series

If you want to run the generate, train, and evaluate pipeline with different parameters after each other you must run the `main_list.py` script (base directory). This time you do not need any arguments, instead you must specify the names of the generated datasets in the script file. You also need the set up the different `main_generate_X.py` files (in the `training/data_generator` folder) where `X = 1,2,3,...` according to the `main_list.py` script.
```sh
python3 main_list.py
```

## Test dataset

The test dataset is located in the `test/test_dataset/test_01` folder. The `test/test_dataset/test_01_show_labels` contains the same images with the annotations draw on them.

Alternatively, the test dataset can be downloaded from here: [link](https://drive.google.com/drive/folders/13xI9df65wbbwL-1jJv0wDc9ksbWD1kMk?usp=sharing)

<img src="figures/industrial_parts.png" alt="drawing" width="400"/>


The selected industrial parts for the case study. Their names in order of their identifier numbers are the following: 1. L-bracket, 2. U-bracket, 3. angle bracket, 4. seat, 5. pipe clamp, 6. handle, 7. bonnet, 8. body, 9. ball, 10. cable shoe. With the letter 'F' the camera holder frame is signed. With the green dashed lines, the borders of the cropped images are shown.


## Results

Our results are placed in the `results/results` folder. The parameters of the data generation process can be found in the `training/training_datasets/saved` folder.

The naming convention is:
1. Monogram of the creator. Example: `HD` (Horváth Dániel)
2. Series number. Example: `H`
3. Identifier number inside the series. Example: `01`
4. Date. Example: `0318`

All together: `HD_H01_0318`

It is important to note that the series before `H` were tested on a slightly different test dataset. To compare the results with the `H series`, the evaluation must be done again. For some cases, it has been already executed. These results are placed in `results/results/other`

### Zero-shot transfer

Our best zero-shot learning method achieved 86.32% mAP@50 on the cropped images. Code name: `HD_H02_0318`.

<img src="figures/ZST_BEST_classes_precision.png" alt="drawing" width="400"/>

### One-shot transfer

Our best zero-shot learning method achieved 97.38% mAP@50 on the cropped images. Code name: `HD_H01_0318`.

<img src="figures/OST_BEST_classes_precision.png" alt="drawing" width="400"/>



## Support

If you have any questions, do not hesitate to contact me:

daniel.horvath - at - sztaki.hu

## Citation

```bibtex
@article{horvath_sim2real_obj_2023,
  title = {Object {Detection} {Using} {Sim2Real} {Domain} {Randomization} for {Robotic} {Applications}},
  volume = {39},
  issn = {1941-0468},
  doi = {10.1109/TRO.2022.3207619},
  url = {http://doi.org/10.1109/TRO.2022.3207619},
  journal = {IEEE Transactions on Robotics},
  author = {Horváth, Dániel and Erdős, Gábor and Istenes, Zoltán and Horváth, Tomáš and Földi, Sándor},
  month = apr,
  year = {2023},
  pages = {1225--1243},
}
```

## License
[MIT](LICENSE)
