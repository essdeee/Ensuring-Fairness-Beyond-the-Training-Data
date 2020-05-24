#!/bin/sh
#
#
#SBATCH --account=free # The account name for the job.
#SBATCH --job-name=Fairness_Checking # The job name.
#SBATCH --mail-type=ALL
#SBATCH --mail-user=sd3013@columbia.edu
#SBATCH --exclusive
#SBATCH -N 1 # The number of cpu cores to use.
#SBATCH --time=4:00:00 # The time the job will take to run.

module load anaconda/3-2019.03
source activate /rigel/home/sd3013/.conda/envs/fairness_checking

#Command to execute Python program
python main.py --solver ECOS --num_cores 14 --T_inner 500 --T 1 --eta_inner 0.5 --gamma_2 0.05 --constraint eo --B 0.1 --no_output y --dataset lawschool --gp_wt_bd 0.03155

python main.py --solver ECOS --num_cores 14 --T_inner 500 --T 1 --eta_inner 0.5 --gamma_2 0.05 --constraint eo --B 0.2 --no_output y --dataset lawschool --gp_wt_bd 0.03155

python main.py --solver ECOS --num_cores 14 --T_inner 500 --T 1 --eta_inner 0.5 --gamma_2 0.05 --constraint eo --B 0.3 --no_output y --dataset lawschool --gp_wt_bd 0.03155

python main.py --solver ECOS --num_cores 14 --T_inner 500 --T 1 --eta_inner 0.5 --gamma_2 0.05 --constraint eo --B 0.4 --no_output y --dataset lawschool --gp_wt_bd 0.03155

python main.py --solver ECOS --num_cores 14 --T_inner 500 --T 1 --eta_inner 0.5 --gamma_2 0.05 --constraint eo --B 0.5 --no_output y --dataset lawschool --gp_wt_bd 0.03155

python main.py --solver ECOS --num_cores 14 --T_inner 500 --T 1 --eta_inner 0.5 --gamma_2 0.05 --constraint eo --B 0.6 --no_output y --dataset lawschool --gp_wt_bd 0.03155

python main.py --solver ECOS --num_cores 14 --T_inner 500 --T 1 --eta_inner 0.5 --gamma_2 0.05 --constraint eo --B 0.7 --no_output y --dataset lawschool --gp_wt_bd 0.03155

python main.py --solver ECOS --num_cores 14 --T_inner 500 --T 1 --eta_inner 0.5 --gamma_2 0.05 --constraint eo --B 0.8 --no_output y --dataset lawschool --gp_wt_bd 0.03155

python main.py --solver ECOS --num_cores 14 --T_inner 500 --T 1 --eta_inner 0.5 --gamma_2 0.05 --constraint eo --B 0.9 --no_output y --dataset lawschool --gp_wt_bd 0.03155

python main.py --solver ECOS --num_cores 14 --T_inner 500 --T 1 --eta_inner 0.5 --gamma_2 0.05 --constraint eo --B 1.0 --no_output y --dataset lawschool --gp_wt_bd 0.03155

#End of script
